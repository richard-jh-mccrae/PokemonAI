"""Restriction-observation boards (ADR-0032 item 6): OBSERVE which heal targets the engine offers,
instead of hand-authoring the clause ``restriction``.

ONE seeded board disambiguates the observable vocabulary in a single offer — a damaged Mega
Evolution Pokémon ex on the Bench plus a damaged non-Mega Active:

  * offers only the bench Mega   -> ``mega_only``
  * offers only the Active       -> ``active_only``
  * offers both                  -> unrestricted

Auto-targeting cards raise no select and fall back to the ``HP_CHANGE`` log's healed serial. A
card whose select never appears and that never heals is an explicit ERROR record, never a guess.
Derivation itself lives in card_effects.py (``derive_restriction``)."""
from __future__ import annotations

from .probe_cards import (
    _AREA_ACTIVE, _AREA_BENCH, _AREA_HAND, _CTX_MAIN, _OPT_ATTACK, _OPT_END,
    _OPT_EVOLVE, _OPT_PLAY, evolution_chain, find_play_option)

_DECK_SIZE = 60
_OPT_CARD = 3       # OptionType.CARD - a select target (area+index+playerIndex)
_OPT_ATTACH = 8     # OptionType.ATTACH
_OPT_RETREAT = 12   # OptionType.RETREAT
_CTX_SETUP_ACTIVE = 1   # SelectContext.SETUP_ACTIVE_POKEMON
_CTX_SETUP_BENCH = 2    # SelectContext.SETUP_BENCH_POKEMON
_CTX_SWITCH = 3         # SelectContext.SWITCH - pick bench body after a retreat
_CTX_REMOVE_DMG = 16    # SelectContext.REMOVE_DAMAGE_COUNTER
_CTX_HEAL = 17          # SelectContext.HEAL
_LOG_HP_CHANGE = 16
_ENERGY_CARD = {0: 3, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}  # EnergyType -> card
_TYPE_INT = {"colorless": 0, "grass": 1, "fire": 2, "water": 3, "lightning": 4,
             "psychic": 5, "fighting": 6, "darkness": 7, "metal": 8, "dragon": 9}

_DEFAULT_MEGA = 678   # Mega Lucario ex - single-hop line (Riolu -> Mega), run-validated
_CHIP_MIN_HP = 150    # only chip bodies this sturdy (frail pre-evo must never be KO'd)
_STURDY_MIN_HP = 180  # bench bodies that can safely take one chip


# --- pure helpers (unit-tested) ------------------------------------------------------

def find_chip_attacker(cards: dict[int, dict]) -> tuple[int | None, int | None]:
    """``(cardId, energyCardId)`` for the opponent's chip attacker: a non-Mega Basic with a VANILLA
    10-60-damage attack payable by 1-2 energy. Deterministic: cheapest, then weakest, then lowest id."""
    best = None
    for cid in sorted(cards):
        c = cards[cid]
        if c.get("category") != "pokemon" or c.get("stage") != "basic" or c.get("megaEx"):
            continue
        own = _TYPE_INT.get(c.get("energy"), 0)
        for a in c.get("attacks") or []:
            cost, dmg = a.get("energies") or [], a.get("damage") or 0
            if not (10 <= dmg <= 60) or len(cost) > 2 or a.get("text"):
                continue
            if all(e in (0, own) for e in cost):
                key = (len(cost), dmg, cid)
                if best is None or key < best[0]:
                    best = (key, cid, _ENERGY_CARD.get(own or 6, 6))
    return (best[1], best[2]) if best else (None, None)


def pick_sturdies(cards: dict[int, dict], exclude_names=(), n: int = 2) -> list[int]:
    """Non-Mega Basics sturdy enough to take a chip (>= _STURDY_MIN_HP), cheapest retreat first — the
    case-B Active must retreat to promote the Mega. Excludes the Mega line's names."""
    cand = [cid for cid, c in cards.items()
            if c.get("category") == "pokemon" and c.get("stage") == "basic"
            and not c.get("megaEx") and (c.get("hp") or 0) >= _STURDY_MIN_HP
            and c.get("name") not in set(exclude_names)]
    cand.sort(key=lambda cid: (cards[cid].get("retreat") or 0, -(cards[cid].get("hp") or 0), cid))
    return cand[:n]


def restriction_deck(target_id: int, cards: dict[int, dict], *, chain: list[int],
                     sturdies: list[int], energy: int) -> list[int]:
    """A legal 60-card observation deck: the trainer under test + the Mega's evolution
    line + the sturdy non-Mega bodies, filled with one basic Energy (retreat fuel)."""
    copies = 1 if cards.get(target_id, {}).get("aceSpec") else 4
    deck = [target_id] * copies
    for cid in list(chain) + list(sturdies):
        deck += [cid] * 4
    deck += [energy] * (_DECK_SIZE - len(deck))
    return deck


def snapshot_board(obs: dict, me: int, cards: dict[int, dict]) -> list[dict]:
    """My in-play bodies with the flags the derivation reads (serial-keyed)."""
    players = (obs.get("current") or {}).get("players") or []
    if me >= len(players):
        return []
    out = []
    for area, arr in ((_AREA_ACTIVE, players[me].get("active") or []),
                      (_AREA_BENCH, players[me].get("bench") or [])):
        for idx, pk in enumerate(arr):
            if not pk:
                continue
            out.append({"serial": pk.get("serial"), "id": pk.get("id"),
                        "area": area, "index": idx,
                        "mega": bool(cards.get(pk.get("id"), {}).get("megaEx")),
                        "active": area == _AREA_ACTIVE,
                        "damaged": (pk.get("hp") or 0) < (pk.get("maxHp") or 0),
                        "hp": pk.get("hp"), "maxHp": pk.get("maxHp"),
                        "name": cards.get(pk.get("id"), {}).get("name")})
    return out


def offered_heal_targets(obs: dict, me: int) -> list[int]:
    """Serials of MY in-play bodies the current select's CARD options point at — the engine's revealed
    target set. Non-CARD options, opponent-side and non-in-play areas do not count."""
    players = (obs.get("current") or {}).get("players") or []
    out: list[int] = []
    for o in (obs.get("select") or {}).get("option") or []:
        if o.get("type") != _OPT_CARD or o.get("playerIndex") != me:
            continue
        if o.get("area") not in (_AREA_ACTIVE, _AREA_BENCH) or me >= len(players):
            continue
        arr = {_AREA_ACTIVE: players[me].get("active"),
               _AREA_BENCH: players[me].get("bench")}[o.get("area")]
        idx = o.get("index")
        pk = arr[idx] if arr and idx is not None and idx < len(arr) else None
        if pk and pk.get("serial") is not None and pk.get("serial") not in out:
            out.append(pk.get("serial"))
    return out


def healed_serials(logs: list[dict], actor: int) -> list[int]:
    """Serials my positive, non-counter HP_CHANGEs healed — the auto-target fallback
    (a card that raises no select still reveals its forced target set)."""
    out: list[int] = []
    for lg in logs or []:
        if (lg.get("type") == _LOG_HP_CHANGE and lg.get("playerIndex") == actor
                and (lg.get("value") or 0) > 0 and not lg.get("putDamageCounter")
                and lg.get("serial") is not None and lg.get("serial") not in out):
            out.append(lg.get("serial"))
    return out


# --- lib drive-shell (run-validated, not unit-tested; lazy `cg` import) --------------

def _hand(obs, me):
    players = obs["current"]["players"]
    return (players[me].get("hand") if me < len(players) else None) or []


def _setup_active_pick(obs, me, want_id):
    """Setup-Active option putting ``want_id`` up, else option 0."""
    hand = _hand(obs, me)
    for i, o in enumerate(obs["select"]["option"]):
        idx = o.get("index")
        if idx is not None and idx < len(hand) and hand[idx].get("id") == want_id:
            return i
    return 0


def _setup_bench_picks(obs, me, line_ids):
    """Bench the line's basics plus sturdies up to 3 total — slots stay free for a
    late-drawn line basic (benching all 5 was the validated deadlock)."""
    sel = obs["select"]
    hand = _hand(obs, me)
    line, rest = [], []
    for i, o in enumerate(sel["option"]):
        idx = o.get("index")
        cid = hand[idx].get("id") if idx is not None and idx < len(hand) else None
        (line if cid in line_ids else rest).append(i)
    picks = (line + rest)[:min(3, sel["maxCount"])]
    if len(picks) < sel["minCount"]:
        picks += [i for i in range(len(sel["option"])) if i not in picks][:sel["minCount"] - len(picks)]
    return picks


def _attach_active_energy(obs, me, cards):
    """Option index attaching a basic Energy from hand to my ACTIVE, or None. Both final bodies must
    hold Energy so energy-discard riders do not skew the offer."""
    hand = _hand(obs, me)
    for i, o in enumerate(obs["select"]["option"]):
        if (o.get("type") == _OPT_ATTACH and o.get("area") == _AREA_HAND
                and o.get("inPlayArea") == _AREA_ACTIVE):
            idx = o.get("index")
            if (idx is not None and idx < len(hand)
                    and cards.get(hand[idx].get("id"), {}).get("category") == "basic_energy"):
                return i
    return None


def _evolve_pick(obs, me, chain):
    """EVOLVE option climbing the line (topmost stage first), preferring the Active."""
    hand = _hand(obs, me)
    best = None
    for stage_id in reversed(chain[1:]):
        for i, o in enumerate(obs["select"]["option"]):
            if o.get("type") != _OPT_EVOLVE or o.get("area") != _AREA_HAND:
                continue
            idx = o.get("index")
            if idx is None or idx >= len(hand) or hand[idx].get("id") != stage_id:
                continue
            if o.get("inPlayArea") == _AREA_ACTIVE:
                return i
            if best is None:
                best = i
        if best is not None:
            return best
    return best


def _bench_pick(obs, me, cards, board, chain):
    """PLAY option to bench a needed Basic: the line's basic when the line has no
    body in play; a sturdy while fewer than 2 are fielded (keeping a line slot)."""
    cur = obs["current"]
    hand = _hand(obs, me)
    line_in_play = any(b["id"] in chain or b["mega"] for b in board)
    n_sturdy = sum(1 for b in board if not b["mega"] and (b["maxHp"] or 0) >= _CHIP_MIN_HP)
    bench_free = (cur["players"][me].get("benchMax") or 5) - len(cur["players"][me].get("bench") or [])
    for i, o in enumerate(obs["select"]["option"]):
        if o.get("type") != _OPT_PLAY:
            continue
        idx = o.get("index")
        cid = hand[idx].get("id") if idx is not None and idx < len(hand) else None
        c = cards.get(cid, {})
        if not (c.get("category") == "pokemon" and c.get("stage") == "basic"):
            continue
        if cid == chain[0] and not line_in_play and bench_free > 0:
            return i
        if (cid != chain[0] and n_sturdy < 2 and bench_free > 0
                and (line_in_play or bench_free >= 2)):
            return i
    return None


def _switch_pick(obs, me, cards, want_mega: bool):
    """After a retreat: the SWITCH option promoting a Mega (or the best non-Mega —
    damaged first, then the sturdiest)."""
    players = obs["current"]["players"]
    best = None
    for i, o in enumerate(obs["select"]["option"]):
        if o.get("type") != _OPT_CARD:
            continue
        arr = {_AREA_ACTIVE: players[me].get("active"),
               _AREA_BENCH: players[me].get("bench")}.get(o.get("area"))
        idx = o.get("index")
        pk = arr[idx] if arr and idx is not None and idx < len(arr) else None
        if not pk:
            continue
        is_mega = bool(cards.get(pk.get("id"), {}).get("megaEx"))
        if want_mega:
            if is_mega:
                return i
        elif not is_mega:
            score = ((pk.get("hp") or 0) < (pk.get("maxHp") or 0), pk.get("maxHp") or 0)
            if best is None or score > best[0]:
                best = (score, i)
    return best[1] if isinstance(best, tuple) else best


def _board_ready(board) -> bool:
    """Damaged Mega on the Bench + damaged non-Mega Active — the discriminating board."""
    return (any(b["mega"] and not b["active"] and b["damaged"] for b in board)
            and any(b["active"] and not b["mega"] and b["damaged"] for b in board))


def _capture_resolution(battle_select, obs, me):
    """Walk the played card's resolution; return ``(offered, contexts, logs)``. Offers come from HEAL /
    REMOVE_DAMAGE_COUNTER selects, recorded BEFORE advancing."""
    offered: list[int] = []
    contexts: list[int] = []
    logs: list[dict] = list(obs.get("logs") or [])
    for _ in range(24):
        cur = obs["current"]
        sel = obs["select"]
        if cur["result"] >= 0 or sel["context"] == _CTX_MAIN or cur["yourIndex"] != me:
            break
        contexts.append(sel["context"])
        pick = None
        if sel["context"] in (_CTX_HEAL, _CTX_REMOVE_DMG):
            for s in offered_heal_targets(obs, me):
                if s not in offered:
                    offered.append(s)
        # prefer damaged own body so optional heals fire
        players = cur["players"]
        for i, o in enumerate(sel["option"]):
            if (o.get("type") == _OPT_CARD and o.get("playerIndex") == me
                    and o.get("area") in (_AREA_ACTIVE, _AREA_BENCH)):
                arr = {_AREA_ACTIVE: players[me].get("active"),
                       _AREA_BENCH: players[me].get("bench")}[o.get("area")]
                idx = o.get("index")
                pk = arr[idx] if arr and idx is not None and idx < len(arr) else None
                if pk and (pk.get("hp") or 0) < (pk.get("maxHp") or 0):
                    pick = i
                    break
        k = min(sel["maxCount"], max(sel["minCount"], 1)) if sel["option"] else 0
        sels = [pick] if (pick is not None and k == 1) else list(range(k))
        obs = battle_select(sels)
        logs += obs.get("logs") or []
    return offered, contexts, logs


def probe_heal_restriction(target_id: int, cards: dict[int, dict], *, me: int = 0,
                           mega_id: int = _DEFAULT_MEGA, max_steps: int = 600) -> dict:
    """Drive the observation board and play ``target_id`` on it; return
    ``{cardId, board, offered, source, contexts, error}`` — ``error`` set rather than a guessed gate."""
    from .probe_cards import _engine, _evolution_data
    chain = evolution_chain(mega_id, _evolution_data())
    if len(chain) < 2 or not cards.get(mega_id, {}).get("megaEx"):
        return {"cardId": target_id, "error": "bad_mega_line", "board": [], "offered": []}
    chip, chip_energy = find_chip_attacker(cards)
    if chip is None:
        return {"cardId": target_id, "error": "no_chip_attacker", "board": [], "offered": []}
    chain_names = {cards.get(c, {}).get("name") for c in chain}
    sturdies = pick_sturdies(cards, exclude_names=chain_names)
    energy = _ENERGY_CARD.get(_TYPE_INT.get(cards.get(chain[0], {}).get("energy"), 6), 6)
    deck = restriction_deck(target_id, cards, chain=chain, sturdies=sturdies, energy=energy)
    battle_start, battle_select, battle_finish = _engine()
    obs, start = battle_start(deck, [chip] * 4 + [chip_energy] * (_DECK_SIZE - 4))
    if start.errorPlayer >= 0:
        battle_finish()
        return {"cardId": target_id, "error": "battle_start_error", "board": [], "offered": []}
    pending_switch = None
    was_ready = False
    try:
        for _ in range(max_steps):
            cur = obs["current"]
            if cur["result"] >= 0:
                return {"cardId": target_id, "board": [], "offered": [],
                        "error": "game_over_before_play"}
            you, ctx = cur["yourIndex"], obs["select"]["context"]
            board = snapshot_board(obs, me, cards)
            if ctx == _CTX_SETUP_ACTIVE and you == me:
                obs = battle_select([_setup_active_pick(obs, me, chain[0])])
            elif ctx == _CTX_SETUP_BENCH and you == me:
                obs = battle_select(_setup_bench_picks(obs, me, set(chain)))
            elif ctx == _CTX_SWITCH and you == me and pending_switch is not None:
                pick = _switch_pick(obs, me, cards, want_mega=pending_switch == "mega")
                pending_switch = None
                obs = battle_select([pick if pick is not None else 0])
            elif ctx != _CTX_MAIN:
                sel = obs["select"]
                mn = sel["minCount"]
                obs = battle_select(list(range(mn)) if mn > 0 else [])
            elif you == me:
                mega_b = next((b for b in board if b["mega"]), None)
                active = next((b for b in board if b["active"]), None)
                if not cur.get("energyAttached"):
                    ai = _attach_active_energy(obs, me, cards)
                    if ai is not None:
                        obs = battle_select([ai])
                        continue
                if mega_b is None:
                    eo = _evolve_pick(obs, me, chain)
                    if eo is not None:
                        obs = battle_select([eo])
                        continue
                bo = _bench_pick(obs, me, cards, board, chain)
                if bo is not None:
                    obs = battle_select([bo])
                    continue
                if _board_ready(board):
                    was_ready = True
                    opt = find_play_option(obs, target_id)
                    if opt is not None:
                        obs = battle_select([opt])
                        offered, contexts, logs = _capture_resolution(battle_select, obs, me)
                        healed = healed_serials(logs, me)
                        source = "select" if offered else ("healed" if healed else None)
                        return {"cardId": target_id, "board": board,
                                "offered": offered or healed, "source": source,
                                "contexts": contexts,
                                "error": None if (offered or healed) else "no_heal_observed"}
                elif mega_b is not None:
                    want = None
                    if not mega_b["active"] and not mega_b["damaged"]:
                        want = "mega"                       # bring Mega up for its chip
                    elif (mega_b["active"] and mega_b["damaged"]
                          and len((cur["players"][me].get("active") or [{}])[0].get("energies") or [])
                          > (cards.get(mega_b["id"], {}).get("retreat") or 0)
                          and any(not b["mega"] and not b["active"]
                                  and (b["damaged"] or (b["maxHp"] or 0) >= _CHIP_MIN_HP)
                                  for b in board)):
                        want = "non_mega"                   # tuck damaged Mega behind
                    if want:
                        ro = next((i for i, o in enumerate(obs["select"]["option"])
                                   if o.get("type") == _OPT_RETREAT), None)
                        if ro is not None:
                            pending_switch = want
                            obs = battle_select([ro])
                            continue
                obs = _end_turn_opt(battle_select, obs)
            else:
                # opponent: fuel up, chip my undamaged sturdy Active, else pass
                if not cur.get("energyAttached"):
                    ai = _attach_any_energy(obs, cards)
                    if ai is not None:
                        obs = battle_select([ai])
                        continue
                act = next((b for b in board if b["active"]), None)
                atk = None
                if act and not act["damaged"] and (act["maxHp"] or 0) >= _CHIP_MIN_HP:
                    atk = _weakest_attack(obs)
                obs = battle_select([atk]) if atk is not None else _end_turn_opt(battle_select, obs)
        return {"cardId": target_id, "board": [], "offered": [],
                "error": "never_playable" if was_ready else "board_never_ready"}
    finally:
        battle_finish()


def _end_turn_opt(battle_select, obs):
    eo = next((i for i, o in enumerate(obs["select"]["option"])
               if o.get("type") == _OPT_END), None)
    return battle_select([eo] if eo is not None else [0])


def _attach_any_energy(obs, cards):
    from .probe_cards import _find_attach_energy
    return _find_attach_energy(obs, cards)


def _weakest_attack(obs):
    """The chip: the opponent's weakest positive attack option (vanilla by deck
    construction), or None."""
    from .probe_cards import _attack_damage
    opts = obs["select"]["option"]
    atks = [i for i, o in enumerate(opts) if o.get("type") == _OPT_ATTACK]
    dmg = _attack_damage()
    pos = [(dmg.get(opts[i].get("attackId"), 0), i) for i in atks]
    pos = [(d, i) for d, i in pos if d > 0]
    return min(pos)[1] if pos else None


def observe_restriction_table(cards: dict[int, dict], table: dict[int, list[dict]], *,
                              retries: int = 3, log=print
                              ) -> tuple[dict[int, dict], dict[int, str], list[int]]:
    """Observe every observable heal-clause card in ``table``; returns ``(measured, errors, skipped)``.
    On error the authored value stays; ``skipped`` lists gates outside the board's vocabulary."""
    from .card_effects import derive_restriction, restriction_observable
    measured: dict[int, dict] = {}
    errors: dict[int, str] = {}
    skipped: list[int] = []
    heal_cards = [cid for cid in sorted(table)
                  if any(c.get("kind") == "heal" for c in table[cid])]
    for cid in heal_cards:
        if not restriction_observable(table[cid]):
            skipped.append(cid)
            continue
        last = "unprobed"
        for _ in range(retries):
            rec = probe_heal_restriction(cid, cards)
            if rec.get("error"):
                last = rec["error"]
                continue
            got = derive_restriction(rec["board"], rec["offered"])
            if "restriction" in got:
                by_serial = {b["serial"]: b for b in rec["board"]}
                measured[cid] = {
                    "restriction": got["restriction"],
                    "offered": [f"{'ACTIVE' if by_serial[s]['active'] else 'BENCH'}:"
                                f"{by_serial[s]['id']} {by_serial[s]['name']}"
                                for s in rec["offered"] if s in by_serial],
                    "source": rec.get("source")}
                last = None
            else:
                last = got["error"]        # a valid record board can't classify
            break
        if last:
            errors[cid] = last
        name = cards.get(cid, {}).get("name")
        if log:
            state = (f"observed {measured[cid]['restriction']!r}" if cid in measured
                     else f"UNOBSERVED ({last})")
            log(f"  {cid} {name}: {state}")
    return measured, errors, skipped
