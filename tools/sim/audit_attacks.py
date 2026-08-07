"""Attack-audit MEASUREMENT harness (ADR-0032 item 5, ADR-0083): drives the native engine and
records what an attack ACTUALLY dealt under a fixed defender panel, plus single-variable sweeps
and a coin fork. Records accumulate in ``reports/attack_audit/measurements.json`` (gitignored).

    python tools/sim/audit_attacks.py --attack 1488          # one attack, whole panel
    python tools/sim/audit_attacks.py --all --limit 50       # batch, resumable
    python tools/sim/audit_attacks.py --attack 300 --sweep   # + energy/hand sweep points

Two layers: the **pure helpers** above the fold are lib-free; the **drive shell** below lazily
imports ``cg``. The REQ-AUDIT ids the tests mark against are reasoned in ADR-0032 and ADR-0083.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_DECK_SIZE = 60
CRUSTLE = 345          # prevent_ex panel body: ability zeroes damage from opponent {ex} Pokémon
_ENERGY_CARD = {0: 3, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}  # EnergyType -> card id
_BENCH_REF = 1         # both seats pinned here unless a bench sweep moves one (REQ-AUDIT-0018)
# A setup miss aborts before the drive plays a turn, so re-dealing is nearly free; a bench miss or
# a timeout has already paid for a whole drive. Hence two very different budgets.
_SETUP_DEALS = 24
_DRIVE_ATTEMPTS = 6
_BENCH_STEPS = (0, 1, 2)
#: Extra DEFENDER attachments (REQ-AUDIT-0020). Step 0 is the panel point itself — the defender
#: never attaches unless a plan asks it to — so only the non-zero steps need their own drive.
_DEF_ENERGY_STEPS = (1, 2)
_SWEEP_POINTS = ({"var": "energy", "step": 1}, {"var": "energy", "step": 2},
                 {"var": "hand", "step": 2}, {"var": "hand", "step": 4},
                 *({"var": "atk_bench", "step": n} for n in _BENCH_STEPS),
                 *({"var": "def_bench", "step": n} for n in _BENCH_STEPS),
                 *({"var": "def_energy", "step": n} for n in _DEF_ENERGY_STEPS))

#: The matched non-{ex} control scenario (REQ-AUDIT-0021): the `def_bench` sweep again with every
#: defender body NOT a Pokemon ex — the only pairing separating `def_ex_in_play` from `def_bench`.
PLAIN_SCENARIO = "vanilla_plain"
#: Defender-composition classes a plan may ask for, as data so `plan_scenarios` and the drive
#: cannot disagree about the vocabulary.
RULE_BOX_EX, RULE_BOX_PLAIN = "ex", "plain"

# Engine vocab (mirrors cg/api.py enums; kept as ints so unit tests stay lib-free).
_OPT_YES, _OPT_NO, _OPT_PLAY, _OPT_ATTACH, _OPT_EVOLVE, _OPT_ATTACK, _OPT_END = 1, 2, 7, 8, 9, 13, 14
_CTX_MAIN, _CTX_SETUP_ACTIVE, _CTX_SETUP_BENCH = 0, 1, 2
_CTX_MULLIGAN, _CTX_ACTIVATE, _CTX_FIRST_EFFECT, _CTX_COIN_HEAD = 42, 43, 44, 46
_AREA_HAND, _AREA_ACTIVE = 2, 4
_LOG_TURN_START, _LOG_TURN_END, _LOG_ATTACK, _LOG_HP_CHANGE, _LOG_COIN = 2, 3, 15, 16, 22


# --- pure helpers ------------------------------------------------------------------------


def evolution_chain(target_id: int, cards: dict[int, dict]) -> list[int]:
    """Basic-first line ending at ``target_id``, walking ``evolvesFrom`` names (lowest id wins).
    A Basic returns ``[target_id]``."""
    by_name: dict[str, list[int]] = {}
    for cid, c in cards.items():
        by_name.setdefault(c.get("name"), []).append(cid)
    chain, seen, cur = [target_id], {target_id}, target_id
    while True:
        pre = cards.get(cur, {}).get("evolvesFrom")
        cand = sorted(c for c in by_name.get(pre, []) if c not in seen) if pre else []
        if not cand:
            break
        cur = cand[0]
        chain.append(cur)
        seen.add(cur)
    chain.reverse()
    return chain


def build_side_deck(chain: list[int], energy_types: list[int],
                    fodder: list[int] = (), fodder_copies: int = 4) -> list[int]:
    """Legal 60-card deck: 4x each chain card + ``fodder_copies`` of each fodder body + Energy
    fill. Colorless in ``energy_types`` maps to Water."""
    fill = sorted({_ENERGY_CARD.get(int(e), 3) for e in (energy_types or [0])}) or [3]
    deck: list[int] = []
    for cid in chain:
        deck += [cid] * 4
    for cid in fodder:
        deck += [cid] * fodder_copies
    i = 0
    while len(deck) < _DECK_SIZE:
        deck.append(fill[i % len(fill)])
        i += 1
    return deck


def _panel_body(cards: dict[int, dict], pred) -> int | None:
    """Highest-HP basic, ability-free, non-Tera Pokémon matching ``pred`` (deterministic)."""
    pool = [(c["hp"], -cid, cid) for cid, c in cards.items()
            if c.get("pokemon") and c.get("basic") and not c.get("hasAbility")
            and not c.get("tera") and pred(c)]
    return max(pool)[2] if pool else None


def not_rule_box(card: dict) -> bool:
    """NOT a Pokemon ex — the matched control's predicate (REQ-AUDIT-0021). A Mega Evolution
    Pokemon ex IS a Pokemon ex (`docs/rulebook.txt` Appendix 1), so ``megaEx`` must be tested too."""
    return not card.get("ex") and not card.get("megaEx")


def bench_fodder(cards: dict[int, dict], exclude: set[int], n: int = 2, pred=None) -> list[int]:
    """``n`` distinct sturdy bench bodies (basic, no ability, non-Tera, top HP); ``exclude`` keeps
    the defender's own line out. Ranking by HP alone makes this bench {ex}-SATURATED — hence ``pred``."""
    pool = sorted((c for c in cards
                   if cards[c].get("pokemon") and cards[c].get("basic")
                   and not cards[c].get("hasAbility") and not cards[c].get("tera")
                   and c not in exclude and (pred is None or pred(cards[c]))),
                  key=lambda c: (-cards[c]["hp"], c))
    return pool[:n]


def _fodder_copies(need: int, bodies: int = 2) -> int:
    """Copies of EACH fodder body: the fewest that can fill a bench target of ``need``. Off-chain
    Basics are not free — each one can satisfy setup instead, stranding an unevolvable Active."""
    return max(1, min(4, -(-need // max(1, bodies))))


def pick_panel(attacker: dict, cards: dict[int, dict],
               extra: dict[str, object] | None = None) -> dict[str, int | None]:
    """The fixed defender panel (REQ-AUDIT-0001) -> ``{scenario: defenderCardId | None}``; None
    marks a could-not-measure scenario. ``extra`` adds ``{scenario: predicate}`` bodies."""
    t = attacker.get("energyType")
    panel = {
        "vanilla": _panel_body(cards, lambda c: c.get("weakness") != t and c.get("resistance") != t),
        "weak": _panel_body(cards, lambda c: c.get("weakness") == t),
        "resist": _panel_body(cards, lambda c: c.get("resistance") == t),
        "prevent_ex": CRUSTLE if (attacker.get("ex") or attacker.get("megaEx")) else None,
    }
    for name, pred in (extra or {}).items():
        panel[name] = _panel_body(cards, pred)
    return panel


def plain_vanilla_pred(attacker: dict):
    """The matched control's panel predicate: the `vanilla` filter plus NOT a Pokemon ex, so the
    control differs from its pair in exactly ONE variable (ADR-0083 §3)."""
    t = attacker.get("energyType")
    return lambda c: (c.get("weakness") != t and c.get("resistance") != t and not_rule_box(c))


def plan_scenarios(attacker: dict, cards: dict[int, dict], sweep: bool = False) -> list[dict]:
    """Ordered scenario specs: the panel, plus sweep points on vanilla. Every plan PINS both seats'
    bench counts; a None ``defender`` stays in so the drive emits an error-ledger entry."""
    panel = pick_panel(attacker, cards, extra={PLAIN_SCENARIO: plain_vanilla_pred(attacker)})
    order = ["vanilla", "weak", "resist"] + (["prevent_ex"] if panel["prevent_ex"] else [])
    plans = [{"scenario": s, "defender": panel[s], "extra_energy": 0, "def_extra_energy": 0,
              "delay_turns": 0, "atk_bench": _BENCH_REF, "def_bench": _BENCH_REF,
              "rule_box": RULE_BOX_EX, "sweep": None} for s in order]
    if sweep:
        for pt in _SWEEP_POINTS:
            plans.append({"scenario": "vanilla", "defender": panel["vanilla"],
                          "extra_energy": pt["step"] if pt["var"] == "energy" else 0,
                          "def_extra_energy": pt["step"] if pt["var"] == "def_energy" else 0,
                          "delay_turns": pt["step"] if pt["var"] == "hand" else 0,
                          "atk_bench": pt["step"] if pt["var"] == "atk_bench" else _BENCH_REF,
                          "def_bench": pt["step"] if pt["var"] == "def_bench" else _BENCH_REF,
                          "rule_box": RULE_BOX_EX, "sweep": dict(pt)})
        for n in _BENCH_STEPS:
            plans.append({"scenario": PLAIN_SCENARIO, "defender": panel[PLAIN_SCENARIO],
                          "extra_energy": 0, "def_extra_energy": 0, "delay_turns": 0,
                          "atk_bench": _BENCH_REF, "def_bench": n,
                          "rule_box": RULE_BOX_PLAIN, "sweep": {"var": "def_bench", "step": n}})
    return plans


def board_snapshot(obs: dict, seat: int) -> dict:
    """``{"active": {"serial","hp"}|None, "bench": [{"serial","hp"}...]}`` for one seat."""
    pl = ((obs.get("current") or {}).get("players") or [])
    p = pl[seat] if seat < len(pl) and pl[seat] else {}
    act = next((a for a in (p.get("active") or []) if a), None)
    return {"active": {"serial": act["serial"], "hp": act["hp"]} if act else None,
            "bench": [{"serial": b["serial"], "hp": b["hp"]} for b in (p.get("bench") or []) if b]}


def _seat(obs: dict, seat: int) -> dict:
    pl = ((obs.get("current") or {}).get("players") or [])
    return (pl[seat] if seat < len(pl) and pl[seat] else {}) or {}


def in_play_ids(obs: dict, seat: int) -> list[int]:
    """Top-card ids of every body IN PLAY for one seat — Active FIRST, then Bench. Active is
    included because `def_ex_in_play` counts ``gs.in_play()``; bench-only under-counts by one."""
    p = _seat(obs, seat)
    act = next((a for a in (p.get("active") or []) if a), None)
    return ([act.get("id")] if act else []) + [b.get("id") for b in (p.get("bench") or []) if b]


def rule_box_count(obs: dict, seat: int, cards: dict[int, dict]) -> int:
    """``{ex}`` bodies in play for one seat (REQ-AUDIT-0021), Mega Evolution Pokemon ex included.
    An unknown card id counts as NOT a rule box."""
    return sum(1 for cid in in_play_ids(obs, seat)
               if (cards.get(cid) or {}).get("ex") or (cards.get(cid) or {}).get("megaEx"))


def bench_stage2_count(obs: dict, seat: int, cards: dict[int, dict]) -> int:
    """Stage 2 bodies on one seat's BENCH (REQ-AUDIT-0021) — `atk_bench_stage2`'s own count. The
    Active is excluded because the variable is "on your Bench" (attack 390's printed sentence)."""
    return sum(1 for b in (_seat(obs, seat).get("bench") or []) if b
               and (cards.get(b.get("id")) or {}).get("stage2"))


def attack_window(logs: list[dict], attack_id: int) -> list[dict]:
    """The target attack's ATTACK log up to the next turn boundary. From the LAST matching log:
    engine log chunks are per-viewing-player and OVERLAP, so only the final chunk is complete."""
    s = max((i for i, l in enumerate(logs)
             if l.get("type") == _LOG_ATTACK and l.get("attackId") == attack_id), default=None)
    if s is None:
        return []
    e = next((j for j in range(s + 1, len(logs))
              if logs[j].get("type") in (_LOG_TURN_START, _LOG_TURN_END)), len(logs))
    return logs[s:e]


def damage_from_window(window: list[dict], defender_snap: dict, attacker_snap: dict) -> dict:
    """Dealt damage by slot (REQ-AUDIT-0004) -> ``{dealtActive, dealtBench, dealtSelf, coinLogs,
    koed}``. Snapshots are taken BEFORE the attack. Negative ``HP_CHANGE`` only — heals never count."""
    dmg: dict[int, int] = {}
    coins = 0
    for l in window:
        if l.get("type") == _LOG_HP_CHANGE and (l.get("value") or 0) < 0:
            dmg[l.get("serial")] = dmg.get(l.get("serial"), 0) - l["value"]
        elif l.get("type") == _LOG_COIN:
            coins += 1
    act = defender_snap.get("active")
    dealt_active = dmg.get(act["serial"], 0) if act else 0
    dealt_bench = [d for d in (dmg.get(b["serial"], 0) for b in defender_snap.get("bench", []))
                   if d]
    my = attacker_snap.get("active")
    dealt_self = dmg.get(my["serial"], 0) if my else 0
    return {"dealtActive": dealt_active, "dealtBench": dealt_bench, "dealtSelf": dealt_self,
            "coinLogs": coins, "koed": bool(act and dealt_active >= act["hp"])}


def shape_record(*, attack_id: int, attacker_id: int, scenario: str, printed: int,
                 defender_id: int, defender_hp: int, damage: dict, energies: int,
                 hand_size: int, coin: str | None, sweep: dict | None,
                 defender_bench: int = 0, attacker_bench: int = 0,
                 defender_energies: int = 0, defender_ex_in_play: int = 0,
                 attacker_bench_stage2: int = 0) -> dict:
    """One measurement record (REQ-AUDIT-0005). ``koed`` marks a right-censored dealtActive. Every
    controlled variable is recorded on EVERY record: ADR-0083 §2 fits only what a sweep RECORDS."""
    return {"attackId": attack_id, "attackerCardId": attacker_id, "scenario": scenario,
            "printed": printed, "dealtActive": damage["dealtActive"],
            "dealtBench": damage["dealtBench"], "dealtSelf": damage["dealtSelf"],
            "defenderCardId": defender_id, "defenderHp": defender_hp,
            "defenderBench": defender_bench, "attackerBench": attacker_bench,
            "defenderExInPlay": defender_ex_in_play,
            "attackerBenchStage2": attacker_bench_stage2,
            "koed": damage["koed"],
            "attackerEnergies": energies, "defenderEnergies": defender_energies,
            "myHandSize": hand_size,
            "coinLogs": damage["coinLogs"], "coin": coin, "sweep": sweep}


def error_record(attack_id: int, attacker_id: int | None, scenario: str, msg: str,
                 sweep: dict | None = None) -> dict:
    """Explicit could-not-measure ledger entry (REQ-AUDIT-0006). Carries the SWEEP point it failed
    on, else every failed sweep shares one :func:`record_key` with the panel record and is lost."""
    return {"attackId": attack_id, "attackerCardId": attacker_id, "scenario": scenario,
            "coin": None, "sweep": sweep, "error": msg}


def record_key(rec: dict) -> tuple:
    """Identity of a measurement — what a re-run replaces (REQ-AUDIT-0007)."""
    sweep = rec.get("sweep") or {}
    return (rec.get("attackId"), rec.get("attackerCardId"), rec.get("scenario"),
            rec.get("coin"), sweep.get("var"), sweep.get("step"))


def merge_records(existing: list[dict], new: list[dict]) -> list[dict]:
    """Union by key: a new measurement wins, but an error never clobbers a success."""
    table = {record_key(r): r for r in existing}
    for r in new:
        k = record_key(r)
        if "error" in r and k in table and "error" not in table[k]:
            continue
        table[k] = r
    return [table[k] for k in sorted(table, key=lambda t: tuple(str(x) for x in t))]


# --- lib drive-shell (lazy ``cg`` import; validated by the engine smoke tests) ------------


def _cg_on_path():
    import sys
    ms = str(Path(__file__).resolve().parents[2] / "src")
    if ms not in sys.path:
        sys.path.insert(0, ms)


def _engine():
    _cg_on_path()
    from cg.game import battle_finish, battle_select, battle_start
    return battle_start, battle_select, battle_finish


_POOL = None      # lazy plain-dict card pool
_ATTACKS = None   # lazy {attackId: {"name","damage","energies","owner"}}



def card_pool() -> dict[int, dict]:
    """Plain-dict card pool from the engine (built once) — feeds the pure helpers."""
    global _POOL
    if _POOL is None:
        _cg_on_path()
        from cg.api import CardType, all_card_data
        _POOL = {c.cardId: {
            "name": c.name, "pokemon": c.cardType == CardType.POKEMON, "basic": c.basic,
            "hp": c.hp, "energyType": (int(c.energyType) if c.energyType is not None else None),
            "weakness": (int(c.weakness) if c.weakness is not None else None),
            "resistance": (int(c.resistance) if c.resistance is not None else None),
            "hasAbility": bool(c.skills), "tera": c.tera, "ex": c.ex, "megaEx": c.megaEx,
            "stage2": bool(getattr(c, "stage2", False)),   # `attackerBenchStage2`'s own predicate
            "evolvesFrom": c.evolvesFrom} for c in all_card_data()}
    return _POOL


def attack_index() -> dict[int, dict]:
    """``{attackId: {name, damage, energies, owner}}`` — owner = lowest cardId carrying it."""
    global _ATTACKS
    if _ATTACKS is None:
        _cg_on_path()
        from cg.api import all_attack, all_card_data
        _ATTACKS = {a.attackId: {"name": a.name, "damage": int(a.damage),
                                 "energies": [int(e) for e in a.energies], "owner": None}
                    for a in all_attack()}
        for c in sorted(all_card_data(), key=lambda c: c.cardId, reverse=True):
            for aid in c.attacks:
                if aid in _ATTACKS:
                    _ATTACKS[aid]["owner"] = c.cardId      # reverse-sorted -> lowest id wins
    return _ATTACKS


def _hand(obs, seat):
    pl = (obs.get("current") or {}).get("players") or []
    return ((pl[seat] or {}).get("hand") if seat < len(pl) else None) or []


def _active(obs, seat):
    pl = (obs.get("current") or {}).get("players") or []
    return next((a for a in ((pl[seat] or {}).get("active") or []) if a), None) \
        if seat < len(pl) else None


def _setup_pick(obs, seat, want_id):
    """Setup-active option index placing ``want_id``, else 0."""
    hand = _hand(obs, seat)
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        idx = o.get("index")
        if idx is not None and idx < len(hand) and hand[idx].get("id") == want_id:
            return i
    return 0


def _find_evolve(obs, seat, evolved_id):
    """EVOLVE option index evolving the ACTIVE into ``evolved_id``, or None."""
    hand = _hand(obs, seat)
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        if (o.get("type") == _OPT_EVOLVE and o.get("area") == _AREA_HAND
                and o.get("inPlayArea") == _AREA_ACTIVE):
            idx = o.get("index")
            if idx is not None and idx < len(hand) and hand[idx].get("id") == evolved_id:
                return i
    return None


def _missing_typed(cost: list[int], attached: list[int]) -> set[int]:
    """Energy card ids still needed for the TYPED part of ``cost`` (colorless excluded) —
    attaching off-type first can deadlock an affordable attack (W,W never pays {G}{C})."""
    missing = set()
    for t in set(cost):
        if t and cost.count(t) > attached.count(t):
            missing.add(_ENERGY_CARD.get(int(t), 3))
    return missing


def _find_attach(obs, seat, prefer: set[int] = frozenset()):
    """ATTACH option index putting a basic Energy from hand onto the ACTIVE (``prefer``red
    card ids first, so typed costs fill before colorless padding), or None."""
    hand = _hand(obs, seat)
    energy_ids = set(_ENERGY_CARD.values())
    fallback = None
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        if (o.get("type") == _OPT_ATTACH and o.get("area") == _AREA_HAND
                and o.get("inPlayArea") == _AREA_ACTIVE):
            idx = o.get("index")
            cid = hand[idx].get("id") if idx is not None and idx < len(hand) else None
            if cid in prefer:
                return i
            if cid in energy_ids and fallback is None:
                fallback = i
    return fallback


def _find_attack_opt(obs, attack_id):
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        if o.get("type") == _OPT_ATTACK and o.get("attackId") == attack_id:
            return i
    return None


def _find_bench_play(obs, seat, cards):
    """PLAY option index benching a basic Pokémon from hand, or None (drawn spares -> bench,
    so snipe/spread riders have live targets)."""
    hand = _hand(obs, seat)
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        if o.get("type") == _OPT_PLAY:
            idx = o.get("index")
            c = cards.get(hand[idx].get("id")) if idx is not None and idx < len(hand) else None
            if c and c.get("pokemon") and c.get("basic"):
                return i
    return None


def _yes_no(obs, want_yes):
    t = _OPT_YES if want_yes else _OPT_NO
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        if o.get("type") == t:
            return [i]
    return [0]


def _generic_advance(sel):
    """Engage a sub-decision: take max(min,1) options so optional effects fire (probe policy)."""
    n = len(sel.get("option") or [])
    k = min(sel.get("maxCount", 0), max(sel.get("minCount", 0), 1), n)
    return list(range(k))


def _sub_select(obs, cap: int | None = None):
    """Selection for a non-MAIN context: YES on activate-style prompts, else generic. ``cap`` bounds
    the SETUP bench too (REQ-AUDIT-0018) — main-phase-only would leak an uncontrolled count."""
    sel = obs.get("select") or {}
    ctx = sel.get("context")
    if ctx in (_CTX_ACTIVATE, _CTX_FIRST_EFFECT):
        return _yes_no(obs, True)
    if ctx == _CTX_SETUP_BENCH:
        n = sel.get("maxCount", 0)
        return list(range(n if cap is None else min(n, cap)))
    return _generic_advance(sel)


def _end_turn(obs):
    for i, o in enumerate((obs.get("select") or {}).get("option") or []):
        if o.get("type") == _OPT_END:
            return [i]
    return _generic_advance(obs.get("select") or {})


def _bench_target(seat: int, cap: int | None) -> int:
    """How many bodies ``seat`` must have benched before the attack may fire (REQ-AUDIT-0018). A cap
    is a TARGET, not a ceiling: a ceiling fires at whatever the shuffle benched."""
    return (1 if seat == 1 else 0) if cap is None else cap


def _benches_ready(obs, caps: dict) -> bool:
    """Both seats have reached their bench targets."""
    return all(len(board_snapshot(obs, seat)["bench"]) >= _bench_target(seat, caps.get(seat))
               for seat in (0, 1))


class _Timeout(Exception):
    pass


class _SetupMiss(Exception):
    """EITHER seat's setup Active is off-chain, so the chain tip can never come online — abort fast
    and retry. Both seats: nothing promotes a benched body here, so a fodder Active is stuck."""


class _BenchMiss(Exception):
    """A bench COUNT or defender-Energy target was not reached within patience, so this shuffle
    cannot produce a CONTROLLED point. The last attempt records the ACTUAL counts instead."""


def _def_energy_ready(obs, target: int) -> bool:
    """The defender's Active has reached its attached-Energy target (REQ-AUDIT-0020)."""
    if not target:
        return True
    d = _active(obs, 1)
    return d is not None and len(d.get("energies") or []) >= target


def _drive_to_attack(battle_select, obs, *, attack_id, atk_chain, def_chain, cost,
                     extra_energy, delay_turns, cards, max_steps, bench_patience=10,
                     atk_bench=None, def_bench=None, def_extra_energy=0):
    """Advance the battle until seat 0 is ready to fire ``attack_id``; returns the pre-attack obs.
    When ``bench_patience`` runs out it fires anyway, and the record carries the ACTUAL counts."""
    delay_left, bench_wait = delay_turns, bench_patience
    caps = {0: atk_bench, 1: def_bench}
    for _ in range(max_steps):
        cur = obs.get("current") or {}
        if cur.get("result", -1) != -1:
            reason = next((l.get("reason") for l in reversed(obs.get("logs") or [])
                           if l.get("type") == 23), None)         # RESULT log carries why
            raise _Timeout(f"match ended before the attack could fire "
                           f"(result={cur.get('result')}, reason={reason}, "
                           f"turn={cur.get('turn')})")
        sel = obs.get("select") or {}
        seat, ctx = cur.get("yourIndex", 0), sel.get("context")
        chain = atk_chain if seat == 0 else def_chain
        if ctx == _CTX_MULLIGAN:
            obs = battle_select(_yes_no(obs, chain[0] not in [c.get("id") for c in _hand(obs, seat)]))
        elif ctx == _CTX_SETUP_ACTIVE:
            if chain[0] not in [c.get("id") for c in _hand(obs, seat)]:
                raise _SetupMiss(f"seat {seat} set up without its chain basic {chain[0]}")
            obs = battle_select([_setup_pick(obs, seat, chain[0])])
        elif ctx != _CTX_MAIN:
            obs = battle_select(_sub_select(obs, cap=caps.get(seat)))
        else:
            defender = _active(obs, 1)
            if defender is not None and defender.get("id") not in def_chain:
                raise _SetupMiss()
            act = _active(obs, seat)
            tip = act is not None and act.get("id") == chain[-1]
            if not tip and act is not None:
                nxt = chain.index(act["id"]) + 1 if act["id"] in chain else None
                eo = _find_evolve(obs, seat, chain[nxt]) if nxt is not None and nxt < len(chain) \
                    else None
                if eo is not None:
                    obs = battle_select([eo])
                    continue
            cap = caps.get(seat)
            if cap is None or len(board_snapshot(obs, seat)["bench"]) < cap:
                bo = _find_bench_play(obs, seat, cards)
                if bo is not None:
                    obs = battle_select([bo])
                    continue
            if seat != 0:
                # The defender ATTACHES when its plan asks it to (REQ-AUDIT-0020). One per turn,
                # so a target of 2 costs the attacker two extra waits.
                if not cur.get("energyAttached") and not _def_energy_ready(obs, def_extra_energy):
                    ao = _find_attach(obs, seat)
                    if ao is not None:
                        obs = battle_select([ao])
                        continue
                obs = battle_select(_end_turn(obs))        # defender sits (evolves, never attacks)
                continue
            attached = [int(e) for e in ((act or {}).get("energies") or [])]
            missing = _missing_typed(cost, attached)
            if (tip and not cur.get("energyAttached")
                    and (missing or len(attached) < len(cost) + extra_energy)):
                ao = _find_attach(obs, seat, prefer=missing)
                if ao is not None:
                    obs = battle_select([ao])
                    continue
            opp = _active(obs, 1)
            opp_ready = opp is not None and opp.get("id") == def_chain[-1]
            atk_opt = _find_attack_opt(obs, attack_id)
            if (tip and atk_opt is not None and len(attached) >= len(cost) + extra_energy
                    and opp_ready):
                if bench_wait > 0 and not (_benches_ready(obs, caps)
                                           and _def_energy_ready(obs, def_extra_energy)):
                    bench_wait -= 1                        # let both seats reach their targets
                    obs = battle_select(_end_turn(obs))
                    continue
                if delay_left > 0:
                    delay_left -= 1                        # hand-size sweep -- wait a turn
                    obs = battle_select(_end_turn(obs))
                    continue
                return obs
            obs = battle_select(_end_turn(obs))
    raise _Timeout("attack never became available")


def _fire_and_measure(battle_select, obs, attack_id, max_resolve=24):
    """Select the attack, resolve its sub-decisions, and extract the dealt-damage split."""
    snap_def, snap_atk = board_snapshot(obs, 1), board_snapshot(obs, 0)
    energies = len((_active(obs, 0) or {}).get("energies") or [])
    hand_size = len(_hand(obs, 0))
    logs: list[dict] = []
    obs = battle_select([_find_attack_opt(obs, attack_id)])
    logs += obs.get("logs") or []
    for _ in range(max_resolve):
        cur = obs.get("current") or {}
        sel = obs.get("select")
        if (cur.get("result", -1) != -1 or sel is None or cur.get("yourIndex") != 0
                or sel.get("context") == _CTX_MAIN):
            break
        obs = battle_select(_sub_select(obs))
        logs += obs.get("logs") or []
    window = attack_window(logs, attack_id)
    if not window:
        raise _Timeout("attack selected but no ATTACK log observed")
    return damage_from_window(window, snap_def, snap_atk), energies, hand_size


def _coin_fork(obs, attack_id, atk_deck, def_deck, max_depth=24, max_leaves=64):
    """Fork the pre-attack position with ``manual_coin=True``, walking BOTH outcomes of every coin
    select (REQ-AUDIT-0009) -> ``(min, max)``, or None when no coin surfaced or the search errored."""
    if not obs.get("search_begin_input"):
        return None
    _cg_on_path()
    from dataclasses import asdict

    from cg import api as cgapi
    cur = obs.get("current") or {}
    players = cur.get("players") or []
    me, opp = players[0] or {}, players[1] or {}
    snap_def, snap_atk = board_snapshot(obs, 1), board_snapshot(obs, 0)

    def obs_dict(state):
        return asdict(state.observation)

    leaves: list[dict] = []
    saw_coin = False
    try:
        root = cgapi.search_begin(
            cgapi.to_observation_class(obs),
            atk_deck[: me.get("deckCount", 0)], atk_deck[: len(me.get("prize") or [])],
            def_deck[: opp.get("deckCount", 0)], def_deck[: len(opp.get("prize") or [])],
            def_deck[: opp.get("handCount", 0)], [], manual_coin=True)
        atk_opt = _find_attack_opt(obs, attack_id)
        stack = [(cgapi.search_step(root.searchId, [atk_opt]), [], 0)]
        while stack and len(leaves) < max_leaves:
            state, logs, depth = stack.pop()
            o = obs_dict(state)
            logs = logs + (o.get("logs") or [])
            c = o.get("current") or {}
            sel = o.get("select")
            done = (c.get("result", -1) != -1 or sel is None or c.get("yourIndex") != 0
                    or sel.get("context") == _CTX_MAIN or depth >= max_depth)
            if done:
                win = attack_window(logs, attack_id)
                if win:
                    leaves.append(damage_from_window(win, snap_def, snap_atk))
                continue
            if sel.get("context") == _CTX_COIN_HEAD:
                saw_coin = True
                for branch in (True, False):
                    stack.append((cgapi.search_step(state.searchId, _yes_no(o, branch)),
                                  logs, depth + 1))
            else:
                stack.append((cgapi.search_step(state.searchId, _sub_select(o)),
                              logs, depth + 1))
        cgapi.search_end()
    except Exception:
        try:
            cgapi.search_end()
        except Exception:
            pass
        return None
    if not saw_coin or not leaves:
        return None
    rank = sorted(leaves, key=lambda d: (d["dealtActive"], sum(d["dealtBench"])))
    return rank[0], rank[-1]


def measure_attack(attack_id: int, plan: dict, *, cards: dict[int, dict] | None = None,
                   coin_fork: bool = True, max_steps: int = 700) -> list[dict]:
    """Measure one attack under one :func:`plan_scenarios` entry; always returns >= 1 record, plus
    ``coin: "min"/"max"`` variants when a coin surfaced, or ``[error_record]`` (REQ-AUDIT-0006)."""
    cards = cards or card_pool()
    info = attack_index().get(attack_id)

    def _err(msg, attacker=None):        # one ledger entry shape; the plan identifies the point
        return [error_record(attack_id, attacker, plan["scenario"], msg, plan.get("sweep"))]

    if info is None or info["owner"] is None:
        return _err("unknown attack or no owner card")
    attacker_id = info["owner"]
    if plan["defender"] is None:
        return _err("no qualifying defender in the pool for this scenario", attacker_id)
    atk_chain = evolution_chain(attacker_id, cards)
    def_chain = evolution_chain(plan["defender"], cards)
    own = cards[attacker_id].get("energyType") or 3         # colorless attacker -> Water
    fill = [e or own for e in info["energies"]] or [own]    # colorless cost -> own type effect
    # Fodder only when a plan asks the seat to bench (REQ-AUDIT-0018), at the fewest copies that
    # can reach the target: every extra off-chain Basic is also a setup hazard.
    atk_need = _bench_target(0, plan.get("atk_bench"))
    def_need = _bench_target(1, plan.get("def_bench"))
    def_energy_need = int(plan.get("def_extra_energy") or 0)
    # Only the DEFENDER's fodder is filtered by rule-box class (REQ-AUDIT-0021): narrowing the
    # attacker's pool would change the setup-miss rate on an axis nobody is measuring.
    def_fodder_pred = not_rule_box if plan.get("rule_box") == RULE_BOX_PLAIN else None
    battle_start, battle_select, battle_finish = _engine()
    drives, last_error = 0, "the attack never became measurable"
    for deal in range(_SETUP_DEALS):
        bare = deal >= _SETUP_DEALS - 2     # chain-basics-only tail: setup can no longer miss
        atk_deck = build_side_deck(                         # clauses reference their own Energy
            atk_chain, fill,
            bench_fodder(cards, set(atk_chain)) if atk_need and not bare else [],
            _fodder_copies(atk_need))
        def_deck = build_side_deck(
            def_chain, [0],
            bench_fodder(cards, set(def_chain), pred=def_fodder_pred)
            if def_need and not bare else [],
            _fodder_copies(def_need))
        obs, start = battle_start(atk_deck, def_deck)
        if getattr(start, "errorPlayer", -1) >= 0 or obs is None:
            battle_finish()
            return _err("battle_start rejected the decks", attacker_id)
        try:
            pre = _drive_to_attack(battle_select, obs, attack_id=attack_id, atk_chain=atk_chain,
                                   def_chain=def_chain, cost=info["energies"],
                                   extra_energy=plan["extra_energy"],
                                   delay_turns=plan["delay_turns"], cards=cards,
                                   max_steps=max_steps,
                                   atk_bench=plan.get("atk_bench"),
                                   def_bench=plan.get("def_bench"),
                                   def_extra_energy=def_energy_need)
            bench_size = len(board_snapshot(pre, 1)["bench"])
            atk_bench_size = len(board_snapshot(pre, 0)["bench"])
            def_energies = len((_active(pre, 1) or {}).get("energies") or [])
            def_ex_in_play = rule_box_count(pre, 1, cards)
            atk_bench_stage2 = bench_stage2_count(pre, 0, cards)
            if drives < _DRIVE_ATTEMPTS - 1 and (
                    (atk_bench_size, bench_size) != (atk_need, def_need)
                    or def_energies < def_energy_need):
                raise _BenchMiss()                  # uncontrolled point -- reshuffle and retry
            fork = _coin_fork(pre, attack_id, atk_deck, def_deck) if coin_fork else None
            damage, energies, hand_size = _fire_and_measure(battle_select, pre, attack_id)
            break
        except _SetupMiss as e:
            last_error = f"setup kept missing a chain basic ({e})"
            continue                        # free: the drive aborted before it played a turn
        except _BenchMiss:
            drives += 1
            last_error = (f"bench targets {(atk_need, def_need)} never reached within patience")
        except _Timeout as e:
            drives += 1
            last_error = str(e)
        except Exception as e:                              # never a silent skip
            return _err(f"{type(e).__name__}: {e}", attacker_id)
        finally:
            battle_finish()
        if drives >= _DRIVE_ATTEMPTS:
            return _err(last_error, attacker_id)
    else:
        return _err(last_error, attacker_id)
    common = dict(attack_id=attack_id, attacker_id=attacker_id, scenario=plan["scenario"],
                  printed=info["damage"], defender_id=plan["defender"],
                  defender_hp=cards[plan["defender"]]["hp"], defender_bench=bench_size,
                  attacker_bench=atk_bench_size, defender_energies=def_energies,
                  defender_ex_in_play=def_ex_in_play, attacker_bench_stage2=atk_bench_stage2,
                  energies=energies, hand_size=hand_size, sweep=plan["sweep"])
    out = [shape_record(damage=damage, coin=None, **common)]
    if fork:
        lo, hi = fork
        out.append(shape_record(damage=lo, coin="min", **common))
        out.append(shape_record(damage=hi, coin="max", **common))
    return out


def audit_attack(attack_id: int, *, sweep: bool = False, cards: dict[int, dict] | None = None,
                 max_steps: int = 700) -> list[dict]:
    """Measure one attack across the whole panel (+ sweep points when asked)."""
    cards = cards or card_pool()
    info = attack_index().get(attack_id)
    if info is None or info["owner"] is None:
        return [error_record(attack_id, None, "panel", "unknown attack or no owner card")]
    records: list[dict] = []
    for plan in plan_scenarios(cards[info["owner"]], cards, sweep=sweep):
        records += measure_attack(attack_id, plan, cards=cards, max_steps=max_steps)
    return records


# --- CLI ---------------------------------------------------------------------------------

_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "reports" / "attack_audit" / "measurements.json"


def load_measurements(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("measurements", [])


def save_measurements(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"measurements": records}, indent=1), encoding="utf-8")


def _covered(attack_id: int, existing: list[dict]) -> bool:
    """True when the attack already has a record (success or ledgered error) on every
    non-sweep panel scenario — batch resumability (REQ-AUDIT-0007)."""
    cards = card_pool()
    info = attack_index().get(attack_id)
    if info is None or info["owner"] is None:
        return True
    have = {(r["scenario"], record_key(r)[3:]) for r in existing if r.get("attackId") == attack_id}
    need = {(p["scenario"], (None, None, None)) for p in plan_scenarios(cards[info["owner"]], cards)}
    return need <= have


def main(argv: list[str] | None = None) -> int:
    import os
    if os.environ.get("CG_ENGINE") == "py":     # ADR-0050 M4: measure the cgpy twin —
        _cg_on_path()                           # same harness, engine swapped via alias
        from cgpy.alias import install
        install()

    ap = argparse.ArgumentParser(description="Attack-audit measurement harness (ADR-0032 item 5)")
    ap.add_argument("--attack", type=int, help="measure one attackId across the panel")
    ap.add_argument("--all", action="store_true", help="batch every attack (resumable)")
    ap.add_argument("--limit", type=int, default=0, help="batch: stop after N uncovered attacks")
    ap.add_argument("--sweep", action="store_true", help="add energy/hand sweep points")
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="measurements JSON path")
    args = ap.parse_args(argv)
    if not args.attack and not args.all:
        ap.error("need --attack ID or --all")
    existing = load_measurements(args.out)
    if args.attack:
        targets = [args.attack]
    else:
        targets = [a for a in sorted(attack_index()) if not _covered(a, existing)]
        if args.limit:
            targets = targets[: args.limit]
    for n, aid in enumerate(targets, 1):
        records = audit_attack(aid, sweep=args.sweep)
        existing = merge_records(existing, records)
        save_measurements(args.out, existing)               # write-through -- crash-safe batches
        for r in records:
            tag = f"ERROR {r['error']}" if "error" in r else (
                f"dealt {r['dealtActive']}{'+' + str(r['dealtBench']) if r['dealtBench'] else ''}"
                f"{' [' + r['coin'] + ']' if r['coin'] else ''}")
            print(f"[{n}/{len(targets)}] attack {aid} {r.get('scenario')}: {tag}")
    print(f"-> {args.out} ({len(existing)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
