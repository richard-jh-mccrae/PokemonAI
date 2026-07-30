"""Attack-audit MEASUREMENT harness (ADR-0032 item 5, measurement half).

For a target attack, drives the native engine (like ``probe_resistance.py``) and records what
the attack ACTUALLY dealt under a fixed defender panel — vanilla / weak / resist / prevent_ex
(Crustle 345, ex attackers only) — plus optional single-variable sweeps and a coin fork
(``search_begin(manual_coin=True)``) that measures min/max dealt over both coin outcomes.
Measures only; the prediction diff (the oracle join) is a later step. Records accumulate in
``reports/attack_audit/measurements.json`` (gitignored).

    python tools/sim/audit_attacks.py --attack 1488          # one attack, whole panel
    python tools/sim/audit_attacks.py --all --limit 50       # batch, resumable
    python tools/sim/audit_attacks.py --attack 300 --sweep   # + energy/hand sweep points

Two layers, split like ``probe_cards.py``: **pure helpers** (panel selection, chains, decks,
scenario planning, log-window damage extraction, record shaping, merge) are lib-free and
unit-tested (``tests/test_audit_attacks.py``); the **drive shell** lazily imports ``cg`` and is
covered by engine smokes (``tests/test_audit_attacks_engine.py``).

Requirements:
    REQ-AUDIT-0001  Panel selection from card data: vanilla/weak/resist by the attacker's type
                    (basic, no ability, non-Tera, highest HP); prevent_ex = Crustle 345 for
                    ex/megaEx attackers only; an unmatchable scenario yields None, not a guess.
    REQ-AUDIT-0002  Side decks are legal 60-card: 4x each chain card + basic-Energy fill mapped
                    from the attack's cost (colorless -> a real Energy card).
    REQ-AUDIT-0003  Evolution chains resolve basic-first by walking evolvesFrom names.
    REQ-AUDIT-0004  Dealt damage extracted from the attack log window (ATTACK -> turn boundary):
                    split active/bench/self by serial, KO censoring flagged, coins counted,
                    heals never counted as damage.
    REQ-AUDIT-0005  Records carry attackId/attackerCardId/scenario/printed/dealtActive/
                    dealtBench/defenderCardId/attackerEnergies/myHandSize/coin (+ hp/koed/self).
    REQ-AUDIT-0006  An unmeasurable attack x scenario is an explicit {"error": ...} ledger
                    entry — never a silent skip.
    REQ-AUDIT-0007  Re-runs merge by record key: a new measurement wins, but an error never
                    clobbers an existing success (accumulative, like card_functions).
    REQ-AUDIT-0008  Sweep planning varies exactly ONE state variable (attached energy, my hand
                    size via delayed attack, or one seat's bench) across 2-3 points, only when
                    requested.
    REQ-AUDIT-0018  Per-seat bench counts are CONTROLLED (a target both seats are driven to,
                    within bench patience) and RECORDED on every measurement. Bench population
                    was previously uncontrolled and unrecorded, so it was free to co-vary with
                    the swept variable — which is how a combined-bench scaler came to ship an
                    exact-looking `atk_hand` fit (274 Torcherto).
    REQ-AUDIT-0009  Coin fork: fork the pre-attack position via search_begin(manual_coin=True),
                    walk both outcomes of every coin select, record min and max dealt.
    REQ-AUDIT-0010  Engine smokes reproduce the known goldens: Resistance -30, Weakness x2,
                    Nebula Beam 1488 = 210 vs Crustle, Jetting Blow 1487 = 0 active + 50 bench.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_DECK_SIZE = 60
CRUSTLE = 345          # prevent_ex panel body: ability zeroes damage from opponent {ex} Pokémon
_ENERGY_CARD = {0: 3, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}  # EnergyType -> card id
_BENCH_REF = 1         # both seats pinned here unless a bench sweep moves one (REQ-AUDIT-0018)
_BENCH_STEPS = (0, 1, 2)
_SWEEP_POINTS = ({"var": "energy", "step": 1}, {"var": "energy", "step": 2},
                 {"var": "hand", "step": 2}, {"var": "hand", "step": 4},
                 *({"var": "atk_bench", "step": n} for n in _BENCH_STEPS),
                 *({"var": "def_bench", "step": n} for n in _BENCH_STEPS))

# Engine vocab (mirrors cg/api.py enums; kept as ints so unit tests stay lib-free).
_OPT_YES, _OPT_NO, _OPT_PLAY, _OPT_ATTACH, _OPT_EVOLVE, _OPT_ATTACK, _OPT_END = 1, 2, 7, 8, 9, 13, 14
_CTX_MAIN, _CTX_SETUP_ACTIVE, _CTX_SETUP_BENCH = 0, 1, 2
_CTX_MULLIGAN, _CTX_ACTIVATE, _CTX_FIRST_EFFECT, _CTX_COIN_HEAD = 42, 43, 44, 46
_AREA_HAND, _AREA_ACTIVE = 2, 4
_LOG_TURN_START, _LOG_TURN_END, _LOG_ATTACK, _LOG_HP_CHANGE, _LOG_COIN = 2, 3, 15, 16, 22


# --- pure helpers ------------------------------------------------------------------------


def evolution_chain(target_id: int, cards: dict[int, dict]) -> list[int]:
    """Basic-first line ending at ``target_id``, walking ``evolvesFrom`` names (lowest id wins).

    Args:
        target_id: Card id of the line's tip.
        cards: ``{cardId: {"name", "evolvesFrom", ...}}`` plain dicts.

    Returns:
        e.g. ``[Staryu, Mega Starmie ex]``; a Basic returns ``[target_id]``.
    """
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
                    fodder: list[int] = ()) -> list[int]:
    """Legal 60-card deck: 4x each chain card (+ 4x each fodder body) + Energy fill.

    Args:
        chain: Basic-first evolution line (>= 1 card).
        energy_types: The attack's ``energies`` (EnergyType ints; colorless maps to Water).
        fodder: Extra distinct basics (:func:`bench_fodder`) so a bench reliably exists.
    """
    fill = sorted({_ENERGY_CARD.get(int(e), 3) for e in (energy_types or [0])}) or [3]
    deck: list[int] = []
    for cid in list(chain) + list(fodder):
        deck += [cid] * 4
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


def bench_fodder(cards: dict[int, dict], exclude: set[int], n: int = 2) -> list[int]:
    """``n`` distinct sturdy bench bodies (basic, no ability, non-Tera, top HP) so snipe/spread
    riders have targets; ``exclude`` keeps the defender's own line out (4-copy legality)."""
    pool = sorted((c for c in cards
                   if cards[c].get("pokemon") and cards[c].get("basic")
                   and not cards[c].get("hasAbility") and not cards[c].get("tera")
                   and c not in exclude),
                  key=lambda c: (-cards[c]["hp"], c))
    return pool[:n]


def pick_panel(attacker: dict, cards: dict[int, dict]) -> dict[str, int | None]:
    """The fixed defender panel for one attacker card (REQ-AUDIT-0001).

    Args:
        attacker: Plain card dict (``energyType``, ``ex``, ``megaEx``).
        cards: Plain card pool.

    Returns:
        ``{scenario: defenderCardId | None}`` — None marks a could-not-measure scenario.
    """
    t = attacker.get("energyType")
    return {
        "vanilla": _panel_body(cards, lambda c: c.get("weakness") != t and c.get("resistance") != t),
        "weak": _panel_body(cards, lambda c: c.get("weakness") == t),
        "resist": _panel_body(cards, lambda c: c.get("resistance") == t),
        "prevent_ex": CRUSTLE if (attacker.get("ex") or attacker.get("megaEx")) else None,
    }


def plan_scenarios(attacker: dict, cards: dict[int, dict], sweep: bool = False) -> list[dict]:
    """Ordered scenario specs for one attacker: the panel, plus sweep points on vanilla.

    Args:
        attacker: Plain card dict.
        cards: Plain card pool.
        sweep: Add single-variable sweep points (REQ-AUDIT-0008) when True.

    Returns:
        ``[{"scenario", "defender", "extra_energy", "delay_turns", "atk_bench", "def_bench",
        "sweep"}, ...]`` — a None ``defender`` stays in the plan so the drive emits an
        error-ledger entry.

    Every plan PINS both seats' bench counts (REQ-AUDIT-0018). Bench population used to be
    uncontrolled — both seats benched every drawn basic — which left it free to co-vary with the
    swept variable and let a bench scaler fit hand size (the spurious 274 override). A bench
    sweep moves exactly one seat and pins the other, so the fit stays single-variable.
    """
    panel = pick_panel(attacker, cards)
    order = ["vanilla", "weak", "resist"] + (["prevent_ex"] if panel["prevent_ex"] else [])
    plans = [{"scenario": s, "defender": panel[s], "extra_energy": 0, "delay_turns": 0,
              "atk_bench": _BENCH_REF, "def_bench": _BENCH_REF, "sweep": None} for s in order]
    if sweep:
        for pt in _SWEEP_POINTS:
            plans.append({"scenario": "vanilla", "defender": panel["vanilla"],
                          "extra_energy": pt["step"] if pt["var"] == "energy" else 0,
                          "delay_turns": pt["step"] if pt["var"] == "hand" else 0,
                          "atk_bench": pt["step"] if pt["var"] == "atk_bench" else _BENCH_REF,
                          "def_bench": pt["step"] if pt["var"] == "def_bench" else _BENCH_REF,
                          "sweep": dict(pt)})
    return plans


def board_snapshot(obs: dict, seat: int) -> dict:
    """``{"active": {"serial","hp"}|None, "bench": [{"serial","hp"}...]}`` for one seat."""
    pl = ((obs.get("current") or {}).get("players") or [])
    p = pl[seat] if seat < len(pl) and pl[seat] else {}
    act = next((a for a in (p.get("active") or []) if a), None)
    return {"active": {"serial": act["serial"], "hp": act["hp"]} if act else None,
            "bench": [{"serial": b["serial"], "hp": b["hp"]} for b in (p.get("bench") or []) if b]}


def attack_window(logs: list[dict], attack_id: int) -> list[dict]:
    """Slice ``logs`` to the target attack's resolution: its ATTACK log up to the next turn
    boundary — excludes pre-attack draws and the between-turns checkup (poison ticks).

    From the LAST matching ATTACK log: engine logs are per-viewing-player (each observation
    replays everything since THAT seat's last select), so accumulated chunks overlap — the
    final chunk holds the complete window, and last-occurrence slicing also de-duplicates."""
    s = max((i for i, l in enumerate(logs)
             if l.get("type") == _LOG_ATTACK and l.get("attackId") == attack_id), default=None)
    if s is None:
        return []
    e = next((j for j in range(s + 1, len(logs))
              if logs[j].get("type") in (_LOG_TURN_START, _LOG_TURN_END)), len(logs))
    return logs[s:e]


def damage_from_window(window: list[dict], defender_snap: dict, attacker_snap: dict) -> dict:
    """Dealt damage by slot from an attack window (REQ-AUDIT-0004).

    Args:
        window: Logs from :func:`attack_window` (may span several selects, pre-sliced).
        defender_snap: :func:`board_snapshot` of the defender taken *before* the attack.
        attacker_snap: Same for the attacker (recoil riders).

    Returns:
        ``{"dealtActive", "dealtBench" (bench-order list, zeros dropped), "dealtSelf",
        "coinLogs", "koed"}``. Negative ``HP_CHANGE`` only — heals never count.
    """
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
                 defender_bench: int = 0, attacker_bench: int = 0) -> dict:
    """One measurement record (REQ-AUDIT-0005). ``koed`` marks a right-censored dealtActive;
    ``defenderBench`` = live snipe targets at fire time (a rider that whiffed vs bench=0 is
    distinguishable from a rider that dealt 0).

    BOTH seats' bench counts are recorded (REQ-AUDIT-0018): the combined-bench scaler family
    reads their sum, and recording them unconditionally makes the historical confound — bench
    population co-varying with the swept variable — visible in retrospect rather than silent.
    """
    return {"attackId": attack_id, "attackerCardId": attacker_id, "scenario": scenario,
            "printed": printed, "dealtActive": damage["dealtActive"],
            "dealtBench": damage["dealtBench"], "dealtSelf": damage["dealtSelf"],
            "defenderCardId": defender_id, "defenderHp": defender_hp,
            "defenderBench": defender_bench, "attackerBench": attacker_bench,
            "koed": damage["koed"],
            "attackerEnergies": energies, "myHandSize": hand_size,
            "coinLogs": damage["coinLogs"], "coin": coin, "sweep": sweep}


def error_record(attack_id: int, attacker_id: int | None, scenario: str, msg: str,
                 sweep: dict | None = None) -> dict:
    """Explicit could-not-measure ledger entry (REQ-AUDIT-0006).

    Carries the SWEEP point it failed on. Without it every failed sweep on a given scenario
    shares one :func:`record_key` with the plain panel record, and since an error never clobbers
    a success, the failure is silently dropped — a silent skip, which is the one thing this
    ledger exists to prevent.
    """
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
    """Selection for a non-MAIN context: YES on activate-style prompts, else generic.

    ``cap`` bounds the SETUP bench (REQ-AUDIT-0018) — setup is the second place a seat benches,
    so a cap applied only in the main phase would leak an uncontrolled count past it. None keeps
    the historical behaviour (bench every spare, so snipe/spread riders have targets).
    """
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
    """How many bodies ``seat`` must have benched before the attack may fire (REQ-AUDIT-0018).

    An explicit cap is a TARGET, not merely a ceiling: a ceiling alone would let the attack fire
    at whatever the shuffle happened to bench, which is the uncontrolled confound the cap exists
    to remove. ``None`` reproduces the historical wait exactly — the defender must field a bench
    so snipe/spread riders have a target, and the attacker is unconstrained.
    """
    return (1 if seat == 1 else 0) if cap is None else cap


def _benches_ready(obs, caps: dict) -> bool:
    """Both seats have reached their bench targets."""
    return all(len(board_snapshot(obs, seat)["bench"]) >= _bench_target(seat, caps.get(seat))
               for seat in (0, 1))


class _Timeout(Exception):
    pass


class _SetupMiss(Exception):
    """The defender's setup Active is off-chain (a fodder basic won the slot) — the chain tip
    can never come online, so abort fast and retry on a fresh shuffle."""


class _BenchMiss(Exception):
    """A seat never reached its requested bench count within bench patience, so this shuffle
    cannot produce a CONTROLLED point — retry. The last attempt accepts what it got and records
    the actual counts: an uncontrolled point is dropped by the axis rules, never trusted."""


def _drive_to_attack(battle_select, obs, *, attack_id, atk_chain, def_chain, cost,
                     extra_energy, delay_turns, cards, max_steps, bench_patience=10,
                     atk_bench=None, def_bench=None):
    """Advance the battle until the attacker (seat 0) is ready to fire ``attack_id``.

    The attacker climbs its chain on the Active, banks Energy to ``need + extra``, then waits
    for the defender's Active to be its chain tip (Crustle must be evolved before the hit),
    for the defender to field a bench (up to ``bench_patience`` extra turns, so snipe riders
    have targets), and for ``delay_turns`` hand-growing waits.

    ``atk_bench`` / ``def_bench`` set each seat's bench count (REQ-AUDIT-0018); None keeps the
    historical behaviour. Each is both a ceiling (the seat stops benching once reached) and a
    TARGET (the attack waits, within ``bench_patience``, until both seats reach theirs) — a
    ceiling alone would fire at whatever the shuffle benched, which is the confound the caps
    exist to remove. When patience runs out the attack fires anyway and the record carries the
    ACTUAL counts, so a missed target degrades to a duplicate fit point, never a wrong one.

    Returns the pre-attack observation.
    """
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
                if bench_wait > 0 and not _benches_ready(obs, caps):
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
    """Fork the pre-attack position with ``manual_coin=True``; walk BOTH outcomes of every coin
    select (REQ-AUDIT-0009). Returns ``(min_damage, max_damage)`` dicts ranked by dealt, or
    None when the fork saw no coin (deterministic) or the search errored (never fatal)."""
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
    """Measure one attack under one scenario plan; always returns >= 1 record.

    Args:
        attack_id: Target attack.
        plan: One :func:`plan_scenarios` entry.
        cards: Plain card pool (defaults to the engine's).
        coin_fork: Fork the pre-attack position for coin min/max when the attack flips.
        max_steps: Drive budget before an explicit timeout error entry.

    Returns:
        ``[record]``, plus ``coin: "min"/"max"`` variants when a coin select surfaced,
        or ``[error_record]`` when the scenario could not be driven (REQ-AUDIT-0006).
    """
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
    # The attacker seat carries bench fodder ONLY when a plan asks it to bench (REQ-AUDIT-0018):
    # its own chain basic is otherwise the sole benchable body, so an attacker-bench target would
    # depend on drawing a spare copy. Kept conditional deliberately — fodder displaces Energy fill
    # and lengthens games, and every non-bench measurement should keep the deck it was taken with.
    atk_fodder = bench_fodder(cards, set(atk_chain)) if plan.get("atk_bench") else []
    atk_deck = build_side_deck(atk_chain, fill, atk_fodder)  # clauses reference their own Energy
    battle_start, battle_select, battle_finish = _engine()
    for attempt in range(6):                                # fresh shuffle when setup misses;
        fodder = bench_fodder(cards, set(def_chain)) if attempt < 4 else []
        def_deck = build_side_deck(def_chain, [0], fodder)  # ...fodderless tail can't miss setup
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
                                   def_bench=plan.get("def_bench"))
            bench_size = len(board_snapshot(pre, 1)["bench"])
            atk_bench_size = len(board_snapshot(pre, 0)["bench"])
            if attempt < 5 and (atk_bench_size, bench_size) != (
                    _bench_target(0, plan.get("atk_bench")),
                    _bench_target(1, plan.get("def_bench"))):
                raise _BenchMiss()                  # uncontrolled point -- reshuffle and retry
            fork = _coin_fork(pre, attack_id, atk_deck, def_deck) if coin_fork else None
            damage, energies, hand_size = _fire_and_measure(battle_select, pre, attack_id)
            break
        except _BenchMiss:
            continue                                # fresh shuffle; attempt 5 accepts what it got
        except _SetupMiss:
            if attempt == 5:
                return _err("defender setup kept missing its chain basic", attacker_id)
        except _Timeout as e:
            return _err(str(e), attacker_id)
        except Exception as e:                              # never a silent skip
            return _err(f"{type(e).__name__}: {e}", attacker_id)
        finally:
            battle_finish()
    common = dict(attack_id=attack_id, attacker_id=attacker_id, scenario=plan["scenario"],
                  printed=info["damage"], defender_id=plan["defender"],
                  defender_hp=cards[plan["defender"]]["hp"], defender_bench=bench_size,
                  attacker_bench=atk_bench_size,
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
