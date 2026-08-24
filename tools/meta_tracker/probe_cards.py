"""Engine probe harness: play each card and capture what it does.

Two layers, split for testability and to keep imports lib-free until actually driving the
engine:
  * **pure helpers** (module level, unit-tested) — legal probe-deck construction, finding
    the play option, and extracting the probe record from a post-play observation;
  * a thin **lib shell** (lazy ``cg`` import *inside* the functions, validated by running,
    like ``dump_cards.py``) that drives ``battle_start`` / ``search_begin`` / ``search_step``.

The record it emits is ``{actor, logs, contexts}`` — consumed by
``card_functions.classify_functions`` to derive behavioral tags.
"""
from __future__ import annotations

_DECK_SIZE = 60
_BENCH_BASICS = 4   # distinct Basic Pokémon to seed (4 copies each) -> a fieldable bench
_ENERGY_CARD = {0: 3, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}  # EnergyType -> basic Energy card
_OPT_PLAY = 7    # OptionType.PLAY — `index` = hand position (see cg/api.py)
_OPT_EVOLVE = 9  # OptionType.EVOLVE — `area`+`index` locate the evolution card in hand
_OPT_ABILITY = 10  # OptionType.ABILITY — `area`+`index` locate the Pokémon whose Ability fires
_TRIGGER_SUPPORTERS = 2  # distinct Supporter lines in a triggered-Ability probe deck (see below)


def _first(cards: dict[int, dict], pred) -> int | None:
    """Lowest card id matching ``pred`` (deterministic), or None."""
    return next((cid for cid in sorted(cards) if pred(cards[cid])), None)


def _strip_serials(node):
    """A select record with every ``serial`` dropped. A serial is a position in a SHUFFLED deck, so it
    differs run to run while the select's shape does not."""
    if isinstance(node, dict):
        return {k: _strip_serials(v) for k, v in node.items() if k != "serial"}
    if isinstance(node, list):
        return [_strip_serials(v) for v in node]
    return node


def select_shape(sel: dict) -> dict:
    """The shuffle-INVARIANT shape of one select: what KIND of decision it is. Deliberately drops
    ``n_options`` and the ``deck`` payload — a fixture pinning the count would fail on the shuffle."""
    cc = sel.get("contextCard") or None
    return {"select_type": sel.get("type"),
            "context": sel.get("context"),
            "min_count": sel.get("minCount"),
            "max_count": sel.get("maxCount"),
            "option_types": sorted({o.get("type") for o in (sel.get("option") or [])}),
            "context_card_id": cc.get("id") if cc else None}


def build_probe_deck(target_id: int, cards: dict[int, dict], low_hp: bool = False,
                     search_fodder: bool = False) -> list[int]:
    """A legal 60-card deck stuffed with ``target_id``. ``low_hp`` seeds the FRAILEST Basics for the
    attrition pass; ``search_fodder`` adds frail Basics and a Supporter so a gated search has a target."""
    tcard = cards.get(target_id, {})
    copies = 1 if tcard.get("aceSpec") else 4    # ≤4 same-name cards; ACE SPEC capped at 1
    deck = [target_id] * copies
    # Basic Pokémon: a few DISTINCT ones (4 copies each) so a bench can be fielded and fetch effects
    # have targets. Skip only if the target itself is a Basic. ≤4 same-name keeps copy counts legal.
    if not (tcard.get("category") == "pokemon" and tcard.get("stage") == "basic"):
        hp_key = ((lambda c: (cards[c].get("hp", 0), c)) if low_hp        # frail -> KO'd (attrition)
                  else (lambda c: (-cards[c].get("hp", 0), c)))           # sturdy -> survives chip
        basics = sorted((c for c in cards if cards[c].get("category") == "pokemon"
                         and cards[c].get("stage") == "basic"), key=hp_key)
        for b in basics[:_BENCH_BASICS]:
            deck += [b] * 4
        if search_fodder:
            seeded = set(deck)
            frail = sorted((c for c in cards if cards[c].get("category") == "pokemon"
                            and cards[c].get("stage") == "basic" and c not in seeded),
                           key=lambda c: (cards[c].get("hp", 0), c))      # frailest -> HP-capped fetch
            deck += [b for b in frail[:2] for _ in range(4)]
            sup = _first(cards, lambda c: c.get("category") == "supporter")
            if sup is not None and sup != target_id:
                deck += [sup] * 4                                         # a Supporter-fetch target
    energies = sorted(c for c in cards if cards[c].get("category") == "basic_energy")
    # Stable/chip: one Energy type is enough. Attrition (low_hp) spreads *all* basic Energy so
    # diverse frail attackers can actually pay costs and KO (single type often can't).
    fill = energies if (low_hp and energies) else (energies[:1] or [None])
    i = 0
    while len(deck) < _DECK_SIZE:                    # basic energy exempt from 4-copy cap
        deck.append(fill[i % len(fill)])
        i += 1
    return deck


def find_play_option(obs: dict, target_id: int) -> int | None:
    """Index into ``obs.select.option`` that plays ``target_id`` from hand, or None."""
    cur = obs.get("current") or {}
    you = cur.get("yourIndex")
    players = cur.get("players") or []
    hand = (players[you].get("hand") if you is not None and you < len(players) else None) or []
    for i, opt in enumerate((obs.get("select") or {}).get("option") or []):
        if opt.get("type") == _OPT_PLAY:
            idx = opt.get("index")
            if idx is not None and idx < len(hand) and hand[idx].get("id") == target_id:
                return i
    return None


def find_ability_option(obs: dict, target_id: int, me: int = 0) -> int | None:
    """Index into ``obs.select.option`` that activates ``target_id``'s Ability, or None. An ABILITY
    option points at a Pokémon via ``area`` (ACTIVE/BENCH) + ``index`` (+ ``playerIndex``)."""
    players = (obs.get("current") or {}).get("players") or []
    for i, opt in enumerate((obs.get("select") or {}).get("option") or []):
        if opt.get("type") != _OPT_ABILITY:
            continue
        pi = opt.get("playerIndex")
        pi = me if pi is None else pi
        if pi >= len(players):
            continue
        arr = {_AREA_ACTIVE: players[pi].get("active"),
               _AREA_BENCH: players[pi].get("bench")}.get(opt.get("area"))
        idx = opt.get("index")
        pk = arr[idx] if arr and idx is not None and idx < len(arr) else None
        if pk and pk.get("id") == target_id:
            return i
    return None


def build_pokemon_deck(target_id: int, attack_energies: list[int] | None) -> list[int]:
    """A 60-card deck of the target Pokémon + the basic Energy its cheapest attack needs."""
    types = [_ENERGY_CARD.get(e, 3) for e in (attack_energies or [0])] or [3]
    deck = [target_id] * 4
    i = 0
    while len(deck) < _DECK_SIZE:
        deck.append(types[i % len(types)])
        i += 1
    return deck


def evolution_chain(target_id: int, data: dict[int, dict]) -> list[int]:
    """Basic-first evolution line ending at ``target_id``. Walks ``evolvesFrom`` (a pre-evolution NAME)
    backwards, resolving each name to the lowest card id so reprints are deterministic."""
    by_name: dict[str, list[int]] = {}
    for cid, c in data.items():
        by_name.setdefault(c.get("name"), []).append(cid)
    chain = [target_id]
    seen = {target_id}
    cur = target_id
    while True:
        pre = data.get(cur, {}).get("evolvesFrom")
        cand = sorted(c for c in by_name.get(pre, []) if c not in seen) if pre else []
        if not cand:
            break
        cur = cand[0]
        chain.append(cur)
        seen.add(cur)
    chain.reverse()
    return chain


def build_evolution_deck(chain: list[int], attack_energies: list[int] | None) -> list[int]:
    """A 60-card deck: 4 of each card in the evolution ``chain`` + the target's attack Energy."""
    types = [_ENERGY_CARD.get(e, 3) for e in (attack_energies or [0])] or [3]
    deck: list[int] = []
    for cid in chain:
        deck += [cid] * 4
    i = 0
    while len(deck) < _DECK_SIZE:
        deck.append(types[i % len(types)])
        i += 1
    return deck


def build_trigger_deck(chain: list[int], fill_energy: int,
                       cards: dict[int, dict]) -> list[int]:
    """A 60-card deck for the TRIGGERED-Ability probe: the whole evolution line, several distinct
    Supporters and basic Energy. More lines narrow the exhaustion window but cannot close it."""
    deck: list[int] = []
    for cid in chain:
        deck += [cid] * 4
    sups = [c for c in sorted(cards)
            if cards[c].get("category") == "supporter" and c not in deck][:_TRIGGER_SUPPORTERS]
    for sup in sups:
        deck += [sup] * 4
    while len(deck) < _DECK_SIZE:
        deck.append(fill_energy)
    return deck[:_DECK_SIZE]


def find_evolve_option(obs: dict, evolved_id: int, me: int = 0,
                       in_play_area: int | None = None) -> int | None:
    """Index into ``obs.select.option`` that evolves a field Pokémon into ``evolved_id``, or None. Pass
    ``in_play_area`` to require a particular spot (the drive uses ACTIVE)."""
    cur = obs.get("current") or {}
    you = cur.get("yourIndex", me)
    players = cur.get("players") or []
    hand = (players[you].get("hand") if you is not None and you < len(players) else None) or []
    for i, opt in enumerate((obs.get("select") or {}).get("option") or []):
        if opt.get("type") == _OPT_EVOLVE and opt.get("area") == _AREA_HAND:
            if in_play_area is not None and opt.get("inPlayArea") != in_play_area:
                continue
            idx = opt.get("index")
            if idx is not None and idx < len(hand) and hand[idx].get("id") == evolved_id:
                return i
    return None


def _bench_deck(cards: dict[int, dict], n_distinct: int = 8) -> list[int]:
    """A basics-rich opponent deck (many distinct high-HP Basics) → reliably fields a Bench, so
    spread attacks have surviving targets and a KO'd Active can be replaced (game doesn't end)."""
    basics = sorted((c for c in cards if cards[c].get("category") == "pokemon"
                     and cards[c].get("stage") == "basic"),
                    key=lambda c: (-cards[c].get("hp", 0), c))[:n_distinct]
    deck: list[int] = []
    for b in basics:
        deck += [b] * 4
    energy = _first(cards, lambda c: c.get("category") == "basic_energy")
    deck += [energy] * (_DECK_SIZE - len(deck))
    return deck


def _setup_active_option(obs: dict, target_id: int) -> int | None:
    """Index of the setup option that puts ``target_id`` into the Active spot, or None."""
    cur = obs.get("current") or {}
    you = cur.get("yourIndex")
    players = cur.get("players") or []
    hand = (players[you].get("hand") if you is not None and you < len(players) else None) or []
    for i, opt in enumerate((obs.get("select") or {}).get("option") or []):
        idx = opt.get("index")
        if idx is not None and idx < len(hand) and hand[idx].get("id") == target_id:
            return i
    return None


def extract_probe(obs_after: dict, actor: int) -> dict:
    """Probe record ``{actor, logs, contexts}`` from a post-play observation. ``contexts`` is the
    resulting select context — a sub-decision the play raised. Pure; tolerates missing logs/select."""
    sel = obs_after.get("select") or {}
    contexts = [sel["context"]] if "context" in sel else []
    return {"actor": actor, "logs": obs_after.get("logs") or [], "contexts": contexts}


# --- lib drive-shell (run-validated, not unit-tested; lazy `cg` import) ------------

_CTX_MAIN = 0       # SelectContext.MAIN — a fresh action choice (card has resolved)
_SETUP_ACTIVE = 1   # SelectContext.SETUP_ACTIVE_POKEMON — place the target Active here
_SETUP_BENCH = 2    # SelectContext.SETUP_BENCH_POKEMON — seed the bench here
_OPT_END = 14       # OptionType.END — end my turn
_OPT_ATTACH = 8     # OptionType.ATTACH — manually attach a card to a Pokémon
_OPT_ATTACK = 13    # OptionType.ATTACK
_LOG_DRAW = 4       # LogType.DRAW — one log per drawn card
_LOG_ATTACK = 15    # LogType.ATTACK — attack event (record keeps from here: drops energize/draws)
_LOG_TURN_START = 2  # LogType.TURN_START — a turn boundary (capture must stop here)
_LOG_TURN_END = 3    # LogType.TURN_END
_AREA_HAND = 2      # AreaType.HAND
_AREA_ACTIVE = 4    # AreaType.ACTIVE
_AREA_BENCH = 5     # AreaType.BENCH
_CTX_REMOVE_DMG = 16  # SelectContext.REMOVE_DAMAGE_COUNTER
_CTX_HEAL = 17        # SelectContext.HEAL
_CTX_ACTIVATE = 43    # SelectContext.ACTIVATE — YesNo: "Would you like to activate the effect?"
_OPT_NO = 2           # OptionType.NO
_DRAW_DRIVE_ATTEMPTS = 4


def _attack_turn_logs(logs: list[dict]) -> list[dict]:
    """Slice ``logs`` to the attacking turn: from the first ATTACK to the next turn boundary, so a
    later turn's manual energy attach cannot read as a false ``energy_accel``."""
    s = next((i for i, l in enumerate(logs) if l.get("type") == _LOG_ATTACK), 0)
    e = next((j for j in range(s + 1, len(logs))
              if logs[j].get("type") in (_LOG_TURN_START, _LOG_TURN_END)), len(logs))
    return logs[s:e]


_ATTACK_DMG = None        # lazy {attackId: damage} cache, built once from engine
_ATTACK_ENERGIES = None   # lazy {cardId: cheapest attack's energy list}
_CARD_ENERGY = None       # lazy {cardId: EnergyType int} (a Pokémon's own type)
_ABILITY_MONS = None      # lazy set of cardIds with ≥1 Ability (skill)
_ATTACK_COSTLIEST = None  # lazy {cardId: (attackId, energies)} — priciest attack (effect-bearing)
_EVO_DATA = None          # lazy {cardId: {name, evolvesFrom, stage1, stage2}}


def _cg_on_path():
    import sys
    from pathlib import Path
    ms = str(Path(__file__).resolve().parents[2] / "src")
    if ms not in sys.path:
        sys.path.insert(0, ms)


def _engine():
    """Lazily import the native engine (keeps this module lib-free for unit tests)."""
    _cg_on_path()
    from cg.game import battle_start, battle_select, battle_finish
    return battle_start, battle_select, battle_finish


def _attack_damage():
    """``{attackId: damage}`` from the engine (built once) — lets the opponent pick its
    *weakest* attack so chip damage stays small and combat games run long (more heal windows)."""
    global _ATTACK_DMG
    if _ATTACK_DMG is None:
        _cg_on_path()
        from cg.api import all_attack
        _ATTACK_DMG = {a.attackId: int(a.damage) for a in all_attack()}
    return _ATTACK_DMG


def _card_attack_energies():
    """``{cardId: cheapest attack's energy list}`` from the engine (built once)."""
    global _ATTACK_ENERGIES
    if _ATTACK_ENERGIES is None:
        _cg_on_path()
        from cg.api import all_attack, all_card_data
        ae = {a.attackId: [int(e) for e in a.energies] for a in all_attack()}
        m = {}
        for c in all_card_data():
            ens = [ae[aid] for aid in c.attacks if aid in ae]
            if ens:
                m[c.cardId] = min(ens, key=len)
        _ATTACK_ENERGIES = m
    return _ATTACK_ENERGIES


def _card_attack_costliest():
    """``{cardId: (attackId, energies)}`` for each card's MOST EXPENSIVE attack (built once). Marquee
    effects sit on the costliest attack, not the cheapest."""
    global _ATTACK_COSTLIEST
    if _ATTACK_COSTLIEST is None:
        _cg_on_path()
        from cg.api import all_attack, all_card_data
        ae = {a.attackId: [int(e) for e in a.energies] for a in all_attack()}
        m = {}
        for c in all_card_data():
            costed = [(aid, ae[aid]) for aid in c.attacks if aid in ae]
            if costed:
                m[c.cardId] = max(costed, key=lambda x: len(x[1]))
        _ATTACK_COSTLIEST = m
    return _ATTACK_COSTLIEST


def _evolution_data():
    """``{cardId: {name, evolvesFrom, stage1, stage2}}`` from the engine (built once) — the
    authoritative source for evolution lines (the shipped ``cards.json`` may be stale)."""
    global _EVO_DATA
    if _EVO_DATA is None:
        _cg_on_path()
        from cg.api import all_card_data
        _EVO_DATA = {c.cardId: {"name": c.name, "evolvesFrom": c.evolvesFrom,
                                "stage1": c.stage1, "stage2": c.stage2}
                     for c in all_card_data()}
    return _EVO_DATA


def _attack_option(obs, want_attack):
    """Option index of the desired attack (by ``attackId``); None if not yet available — which makes
    the drive bank more Energy rather than fire a cheap vanilla attack."""
    opts = obs["select"]["option"]
    atks = [i for i, o in enumerate(opts) if o.get("type") == _OPT_ATTACK]
    if not atks:
        return None
    if want_attack is None:
        return atks[0]
    return next((i for i in atks if opts[i].get("attackId") == want_attack), None)


def _card_energy_type():
    """``{cardId: EnergyType int}`` from the engine (built once) — to attach *on-type* Energy
    so energy-hungry Abilities (e.g. discard-an-Energy-to-draw) have fuel."""
    global _CARD_ENERGY
    if _CARD_ENERGY is None:
        _cg_on_path()
        from cg.api import all_card_data
        _CARD_ENERGY = {c.cardId: int(c.energyType) for c in all_card_data()}
    return _CARD_ENERGY


def _ability_pokemon():
    """Set of cardIds that have ≥1 Ability (skill), from the engine (built once). The shipped
    ``cards.json`` lacks ``skills``, so the engine is authoritative for *which* mons to probe."""
    global _ABILITY_MONS
    if _ABILITY_MONS is None:
        _cg_on_path()
        from cg.api import all_card_data
        _ABILITY_MONS = {c.cardId for c in all_card_data() if c.skills}
    return _ABILITY_MONS


def _advance(battle_select, obs):
    """Move past a decision we do not probe. During the setup bench step take ALL offered Pokémon
    (a board enables gust/switch probing); otherwise minCount-first."""
    sel = obs["select"]
    if sel["context"] == _SETUP_BENCH:
        return battle_select(list(range(sel["maxCount"])))
    mn = sel["minCount"]
    return battle_select(list(range(mn)) if mn > 0 else [])


def _end_turn(battle_select, obs):
    """End the current turn (so the next draw happens); fall back to a generic advance."""
    for i, o in enumerate(obs["select"]["option"]):
        if o.get("type") == _OPT_END:
            return battle_select([i])
    return _advance(battle_select, obs)


def _find_attach_energy(obs, cards):
    """Option index that manually attaches a basic Energy from hand, or None."""
    cur = obs["current"]
    hand = cur["players"][cur["yourIndex"]].get("hand") or []
    for i, o in enumerate(obs["select"]["option"]):
        if o.get("type") == _OPT_ATTACH and o.get("area") == _AREA_HAND:
            idx = o.get("index")
            if (idx is not None and idx < len(hand)
                    and cards.get(hand[idx].get("id"), {}).get("category") == "basic_energy"):
                return i
    return None


def _my_active_damaged(obs, me):
    """True if my Active has taken damage (hp < maxHp) — i.e. a heal target exists."""
    act = obs["current"]["players"][me].get("active") or []
    return bool(act) and act[0] is not None and act[0].get("hp", 0) < act[0].get("maxHp", 0)


def _my_discard_stocked(obs, me, cards):
    """True if my discard holds a Pokémon or basic Energy — a target for ``recycle`` effects
    (Night Stretcher / Super Rod). Stocked by my Active being KO'd in the attrition pass."""
    disc = obs["current"]["players"][me].get("discard") or []
    return any(cards.get(c.get("id"), {}).get("category") in ("pokemon", "basic_energy")
               for c in disc)


def _develop(battle_select, obs, cards, attack=False, ko=False):
    """Build the board so energy/heal effects have something to act on. ``attack`` chips slowly (heal
    targets, long games); ``ko`` KOs my frail Active fast (stocks discard → recycle/energy_denial)."""
    if not obs["current"].get("energyAttached"):
        ai = _find_attach_energy(obs, cards)
        if ai is not None:
            return battle_select([ai])
    if attack:
        opts = obs["select"]["option"]
        atk = [i for i, o in enumerate(opts) if o.get("type") == _OPT_ATTACK]
        if atk:
            dmg = _attack_damage()
            scored = [(dmg.get(opts[i].get("attackId"), 0), i) for i in atk]
            positive = [(d, i) for d, i in scored if d > 0]
            if not positive:
                return battle_select([atk[0]])
            pick = max(positive) if ko else min(positive)   # KO fast vs chip slow
            return battle_select([pick[1]])
    return _end_turn(battle_select, obs)


def _damaged_option_indices(obs):
    """Option indices whose referenced Pokémon has taken damage (hp < maxHp)."""
    players = obs["current"]["players"]
    out = []
    for i, o in enumerate(obs["select"]["option"]):
        area, idx, pi = o.get("area"), o.get("index"), o.get("playerIndex")
        if pi is None or idx is None:
            continue
        arr = {_AREA_ACTIVE: players[pi].get("active"),
               _AREA_BENCH: players[pi].get("bench")}.get(area)
        pk = arr[idx] if arr and idx < len(arr) else None
        if pk and pk.get("hp", 0) < pk.get("maxHp", 0):
            out.append(i)
    return out


def _resolve_advance(battle_select, obs):
    """During a card's own resolution, engage sub-decisions so optional effects fire. For a
    heal / remove-damage target choice, prefer a *damaged* Pokémon so the heal actually shows."""
    sel = obs["select"]
    if sel["context"] in (_CTX_REMOVE_DMG, _CTX_HEAL):
        dmg = _damaged_option_indices(obs)
        if dmg:
            return battle_select(dmg[:max(sel["minCount"], 1)])
    k = min(sel["maxCount"], max(sel["minCount"], 1)) if sel["option"] else 0
    return battle_select(list(range(k)))


def _resolve_from(battle_select, obs, actor, max_resolve=16):
    """Resolve forced sub-decisions from ``obs``, accumulating the record. Returns ``(record, obs)`` so
    the caller can keep driving the same turn. Stops at MAIN / match end / the opponent's turn."""
    logs, contexts = [], []
    for _ in range(max_resolve):
        r = extract_probe(obs, actor)
        logs += r["logs"]
        contexts += r["contexts"]
        cur = obs["current"]
        if cur["result"] >= 0 or obs["select"]["context"] == _CTX_MAIN or cur["yourIndex"] != actor:
            break
        obs = _resolve_advance(battle_select, obs)
    return {"actor": actor, "logs": logs, "contexts": contexts}, obs


def _resolve_play(battle_select, obs, opt, actor, max_resolve=16):
    """Play option ``opt`` and resolve the card's forced sub-decisions, accumulating the record."""
    obs = battle_select([opt])
    rec, _ = _resolve_from(battle_select, obs, actor, max_resolve)
    return rec


def _deck_count(obs: dict, player: int) -> int | None:
    players = (obs.get("current") or {}).get("players") or []
    if player >= len(players):
        return None
    deck_count = players[player].get("deckCount")
    return deck_count if isinstance(deck_count, int) else None


def _draw_capture_is_deck_limited(rec: dict | None) -> bool:
    """True when a DRAW capture exactly equals the pre-play deck size — a measurement of deck
    exhaustion, not of the card's printed draw ceiling."""
    if not rec or "deck_count" not in rec:
        return False
    deck_count = rec.get("deck_count")
    if not isinstance(deck_count, int):
        return False
    actor = rec.get("actor")
    draws = sum(1 for lg in rec.get("logs") or []
                if lg.get("playerIndex") == actor and lg.get("type") == _LOG_DRAW)
    return draws > 0 and draws == deck_count


def probe_card(target_id: int, cards: dict[int, dict], *, me: int = 0,
               attack: bool = False, ko: bool = False, max_steps: int = 400,
               drive_attempts: int = _DRAW_DRIVE_ATTEMPTS) -> dict | None:
    """Drive a real game until ``me`` can play ``target_id``; return its probe record (or None). Three
    scenarios: stable, ``attack`` (the opponent chips), ``ko`` (attrition). A deck-limited DRAW retries."""
    last = None
    for _ in range(max(1, drive_attempts)):
        last = _drive_probe_card(target_id, cards, me=me, attack=attack, ko=ko,
                                 max_steps=max_steps)
        if not _draw_capture_is_deck_limited(last):
            return last
    return last


def _drive_probe_card(target_id: int, cards: dict[int, dict], *, me: int = 0,
                      attack: bool = False, ko: bool = False,
                      max_steps: int = 400) -> dict | None:
    """One shuffle's worth of ``probe_card`` — see that function for the contract."""
    combat = attack or ko
    battle_start, battle_select, battle_finish = _engine()
    deck = build_probe_deck(target_id, cards, low_hp=ko, search_fodder=not combat)  # fodder stable-only
    obs, start = battle_start(deck, deck)
    if start.errorPlayer >= 0:
        battle_finish()
        return None
    try:
        for _ in range(max_steps):
            cur = obs["current"]
            if cur["result"] >= 0:
                return None
            you, ctx = cur["yourIndex"], obs["select"]["context"]
            if ctx != _CTX_MAIN:
                obs = _advance(battle_select, obs)             # setup / forced sub-decision
            elif you == me:
                opt = find_play_option(obs, target_id)
                # In combat, hold the target until the scenario's board state is ready (Active
                # damaged for heal, discard stocked for recycle); stable plays as soon as legal.
                ready = _my_discard_stocked(obs, me, cards) if ko else _my_active_damaged(obs, me)
                if opt is not None and (not combat or ready):
                    rec = _resolve_play(battle_select, obs, opt, me)
                    rec["deck_count"] = _deck_count(obs, me)
                    return rec
                obs = _develop(battle_select, obs, cards)                   # I build board, never attack
            else:
                obs = _develop(battle_select, obs, cards, attack=combat, ko=ko)  # opponent chips/KOs
        return None
    finally:
        battle_finish()

def probe_pokemon(target_id: int, cards: dict[int, dict], *, me: int = 0,
                  max_steps: int = 250) -> dict | None:
    """Drive a game to make ``target_id`` (a Pokémon) attack; return its probe record (or None). Both
    benches are seeded so spread/status have targets. Stage 1/2 attackers are not reached."""
    energies = _card_attack_energies().get(target_id)
    if energies is None:
        return None                          # no attack to probe
    battle_start, battle_select, battle_finish = _engine()
    deck = build_pokemon_deck(target_id, energies)
    obs, start = battle_start(deck, deck)
    if start.errorPlayer >= 0:
        battle_finish()
        return None
    try:
        for _ in range(max_steps):
            cur = obs["current"]
            if cur["result"] >= 0:
                return None
            you, ctx = cur["yourIndex"], obs["select"]["context"]
            if ctx == _SETUP_ACTIVE and you == me:
                o = _setup_active_option(obs, target_id)
                obs = battle_select([o] if o is not None else [0])         # put target Active
            elif ctx != _CTX_MAIN:
                obs = _advance(battle_select, obs)                         # setup (benches) / sub-decision
            elif you == me:
                if not cur.get("energyAttached"):
                    ai = _find_attach_energy(obs, cards)
                    if ai is not None:
                        obs = battle_select([ai])
                        continue
                atk = next((i for i, o in enumerate(obs["select"]["option"])
                            if o.get("type") == _OPT_ATTACK), None)
                if atk is not None:
                    obs = battle_select([atk])                            # attack
                    rec = extract_probe(obs, me)
                    rec["logs"] = _attack_turn_logs(rec["logs"])          # this turn only, no energize leak
                    return rec
                obs = _end_turn(battle_select, obs)
            else:
                obs = _end_turn(battle_select, obs)
        return None
    finally:
        battle_finish()


def probe_pokemon_ability(target_id: int, cards: dict[int, dict], *, me: int = 0,
                          max_steps: int = 160) -> dict | None:
    """Drive a game to activate ``target_id``'s Ability; return its probe record (or None). The option
    appears only when the Ability is usable, so passive Abilities never become one."""
    etype = _card_energy_type().get(target_id, 0)
    battle_start, battle_select, battle_finish = _engine()
    deck = build_pokemon_deck(target_id, [etype])
    obs, start = battle_start(deck, deck)
    if start.errorPlayer >= 0:
        battle_finish()
        return None
    try:
        for _ in range(max_steps):
            cur = obs["current"]
            if cur["result"] >= 0:
                return None
            you, ctx = cur["yourIndex"], obs["select"]["context"]
            if ctx == _SETUP_ACTIVE and you == me:
                o = _setup_active_option(obs, target_id)
                obs = battle_select([o] if o is not None else [0])         # put target Active
            elif ctx != _CTX_MAIN:
                obs = _advance(battle_select, obs)                         # setup (benches) / sub-decision
            elif you == me:
                opt = find_ability_option(obs, target_id, me)
                if opt is not None:
                    return _resolve_play(battle_select, obs, opt, me)      # activate + record Ability
                if not cur.get("energyAttached"):
                    ai = _find_attach_energy(obs, cards)
                    if ai is not None:
                        obs = battle_select([ai])                         # bank Energy for next turn
                        continue
                obs = _end_turn(battle_select, obs)
            else:
                obs = _end_turn(battle_select, obs)
        return None
    finally:
        battle_finish()


def probe_evolution(target_id: int, cards: dict[int, dict], *, me: int = 0,
                    max_steps: int = 400) -> dict | None:
    """Drive a game to evolve up to ``target_id`` (Stage 1/2), then capture its Ability and its
    COSTLIEST attack — the one carrying the marquee effect. Trimmed to the ``ATTACK`` event."""
    chain = evolution_chain(target_id, _evolution_data())
    if len(chain) < 2:
        return None                                   # a Basic — probe_pokemon handles it
    costliest = _card_attack_costliest().get(target_id)
    energies = costliest[1] if costliest else [0]
    want_attack = costliest[0] if costliest else None
    battle_start, battle_select, battle_finish = _engine()
    deck = build_evolution_deck(chain, energies)
    obs, start = battle_start(deck, _bench_deck(cards))   # opponent fields a Bench -> spread targets
    if start.errorPlayer >= 0:
        battle_finish()
        return None
    basic = chain[0]
    logs: list = []
    contexts: list = []
    ability_done = False
    try:
        for _ in range(max_steps):
            cur = obs["current"]
            if cur["result"] >= 0:
                break
            you, ctx = cur["yourIndex"], obs["select"]["context"]
            if ctx == _SETUP_ACTIVE and you == me:
                o = _setup_active_option(obs, basic)
                obs = battle_select([o] if o is not None else [0])         # the Basic goes Active
            elif ctx != _CTX_MAIN:
                obs = _advance(battle_select, obs)                         # setup benches / sub-decisions
            elif you == me:
                active = (cur["players"][me].get("active") or [None])[0]
                active_id = active.get("id") if active else None
                if active_id != target_id:
                    eo = None
                    for stage_id in reversed(chain[1:]):                   # evolve Active up the line
                        eo = find_evolve_option(obs, stage_id, me, in_play_area=_AREA_ACTIVE)
                        if eo is not None:
                            break
                    if eo is not None:
                        obs = battle_select([eo]); continue                # evolve one step this turn
                    if not cur.get("energyAttached"):
                        ai = _find_attach_energy(obs, cards)
                        if ai is not None:
                            obs = battle_select([ai]); continue            # bank Energy while waiting to evolve
                    obs = _end_turn(battle_select, obs); continue
                if not ability_done:                                       # target is Active: Ability first
                    ao = find_ability_option(obs, target_id, me)
                    if ao is not None:
                        obs = battle_select([ao])
                        r, obs = _resolve_from(battle_select, obs, me)
                        logs += r["logs"]; contexts += r["contexts"]
                    ability_done = True
                    continue
                atk = _attack_option(obs, want_attack)
                if atk is not None:                                        # fire costliest (effect) attack
                    obs = battle_select([atk])
                    r, obs = _resolve_from(battle_select, obs, me)         # resolve spread placement
                    logs += _attack_turn_logs(r["logs"])                   # this turn only, no energize leak
                    contexts += r["contexts"]
                    break
                if not cur.get("energyAttached"):
                    ai = _find_attach_energy(obs, cards)
                    if ai is not None:
                        obs = battle_select([ai]); continue                # bank Energy for costly attack
                obs = _end_turn(battle_select, obs)
            else:
                obs = _end_turn(battle_select, obs)
    finally:
        battle_finish()
    return {"actor": me, "logs": logs, "contexts": contexts} if (logs or contexts) else None


# --- triggered-Ability shape probe (Issue #305) ------------------------------------

_TRIGGER_RESOLVE_STEPS = 16   # sub-decisions a single trigger may raise before returning to MAIN
_TRIGGER_MENU_STEPS = 24      # drive steps allowed while sampling the MAIN menus that follow


def _capture_trigger(battle_select, obs, opt: int, taken: str, me: int, *,
                     decline: bool, main_menus: int) -> dict:
    """Take option ``opt`` and record every select it raises, then the MAIN menus that follow.
    ``decline`` answers NO to the gate — the strongest form of the question. Every field is invariant."""
    obs = battle_select([opt])
    raw_gate = _strip_serials(obs["select"])
    effect_selects: list[dict] = []
    reached_main = False
    for _ in range(_TRIGGER_RESOLVE_STEPS):
        sel = obs["select"]
        if obs["current"]["result"] >= 0:
            break
        if sel["context"] == _CTX_MAIN:
            reached_main = True
            break
        if sel["context"] != _CTX_ACTIVATE:                 # the gate itself is `raw_gate`
            effect_selects.append(select_shape(sel))
        if decline and sel["context"] == _CTX_ACTIVATE:
            no = next((i for i, o in enumerate(sel["option"]) if o.get("type") == _OPT_NO), 0)
            obs = battle_select([no])
        else:
            k = min(sel["maxCount"], max(sel["minCount"], 1)) if sel["option"] else 0
            obs = battle_select(list(range(k)))

    sampled = n_with_ability = 0
    for _ in range(_TRIGGER_MENU_STEPS):
        if sampled >= main_menus or obs["current"]["result"] >= 0:
            break
        cur, sel = obs["current"], obs["select"]
        if cur["yourIndex"] != me:
            obs = _end_turn(battle_select, obs)
        elif sel["context"] == _CTX_MAIN:
            sampled += 1
            n_with_ability += any(o.get("type") == _OPT_ABILITY for o in (sel.get("option") or []))
            obs = _end_turn(battle_select, obs)
        else:
            obs = _advance(battle_select, obs)

    return {"option_taken": taken, "gate_select": raw_gate, "effect_selects": effect_selects,
            "returned_to_main": reached_main, "main_menus_sampled": sampled,
            "main_menus_with_ability_option": n_with_ability,
            "ability_option_seen": bool(n_with_ability) or
                                   any(_OPT_ABILITY in s["option_types"] for s in effect_selects)}


#: Fresh-shuffle attempts a search-based trigger gets before giving up. MEASURED: single-attempt
#: exhaustion is 0.40% / 1.60% per subject, so 4 attempts put P(all exhaust) at ~1e-8 or below.
_TRIGGER_DRIVE_ATTEMPTS = 4


def _accept_capture_is_exhausted(rec: dict, search_ceiling: int | None) -> bool:
    """True when an ACCEPT capture's search came up short of its own printed ceiling — a shuffle-
    dependent deck shortage, not a fact about the card. A ``None`` ceiling means exactly one find."""
    es = rec["effect_selects"]
    if search_ceiling is None:
        return not es
    return not es or es[0]["max_count"] < search_ceiling


def _gate_was_skipped(rec: dict) -> bool:
    """True when the trigger's gate was never posed at all — TOTAL exhaustion (``deckCount == 0``), so
    the recorded ``gate_select`` is already a MAIN select describing an unrelated decision."""
    return rec["gate_select"]["context"] != _CTX_ACTIVATE


def probe_triggered_ability(target_id: int, cards: dict[int, dict], *, decline: bool = False,
                            me: int = 0, max_steps: int = 400, main_menus: int = 2,
                            search_ceiling: int | None = None,
                            drive_attempts: int = _TRIGGER_DRIVE_ATTEMPTS) -> dict | None:
    """Drive a game until ``target_id`` enters play by the option its TRIGGERED Ability rides, then
    capture the selects that option raises. ``ability_option_seen`` is the answer bit (Issue #305)."""
    for _ in range(max(1, drive_attempts)):
        rec = _drive_to_trigger(target_id, cards, decline=decline, me=me, max_steps=max_steps,
                                main_menus=main_menus)
        if rec is None or _gate_was_skipped(rec):
            continue
        if decline or not _accept_capture_is_exhausted(rec, search_ceiling):
            return rec
    return None                             # every attempt missed setup or came up exhausted


def _drive_to_trigger(target_id: int, cards: dict[int, dict], *, decline: bool, me: int,
                      max_steps: int, main_menus: int) -> dict | None:
    """One shuffle's worth of ``probe_triggered_ability`` — see that function for the contract."""
    chain = evolution_chain(target_id, _evolution_data())
    etype = _card_energy_type().get(target_id, 0)
    battle_start, battle_select, battle_finish = _engine()
    deck = build_trigger_deck(chain, _ENERGY_CARD.get(etype, 3), cards)
    obs, start = battle_start(deck, deck)
    if start.errorPlayer >= 0:
        battle_finish()
        return None
    basic, evolving = chain[0], len(chain) > 1
    try:
        for _ in range(max_steps):
            cur = obs["current"]
            if cur["result"] >= 0:
                return None
            you, ctx = cur["yourIndex"], obs["select"]["context"]
            if ctx == _SETUP_ACTIVE and you == me:
                o = _setup_active_option(obs, basic)
                obs = battle_select([o] if o is not None else [0])          # the line's Basic Active
            elif ctx == _SETUP_BENCH and you == me:
                obs = battle_select(list(range(obs["select"]["minCount"])))  # keep copies in HAND
            elif ctx != _CTX_MAIN:
                obs = _advance(battle_select, obs)                          # setup / sub-decision
            elif you != me:
                obs = _end_turn(battle_select, obs)                         # opponent never acts
            elif not evolving:
                po = find_play_option(obs, target_id)                       # Basic: deploy to Bench
                if po is not None:
                    return _capture_trigger(battle_select, obs, po, "PLAY", me,
                                            decline=decline, main_menus=main_menus)
                obs = _end_turn(battle_select, obs)
            else:
                active = (cur["players"][me].get("active") or [None])[0]
                nxt = chain[chain.index(active.get("id")) + 1] if active and \
                    active.get("id") in chain[:-1] else target_id
                eo = find_evolve_option(obs, nxt, me, in_play_area=_AREA_ACTIVE)
                if eo is not None and nxt == target_id:
                    return _capture_trigger(battle_select, obs, eo, "EVOLVE", me,
                                            decline=decline, main_menus=main_menus)
                obs = battle_select([eo]) if eo is not None else _end_turn(battle_select, obs)
        return None
    finally:
        battle_finish()
