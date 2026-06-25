"""Engine probe harness: play each card and capture what it does (see docs/card-functions.md).

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
_BENCH_BASICS = 4   # distinct Basic Pokémon to seed (4 copies each) → a fieldable bench
_ENERGY_CARD = {0: 3, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}  # EnergyType -> basic Energy card
_OPT_PLAY = 7    # OptionType.PLAY — its `index` is the hand position (see cg/api.py)
_OPT_EVOLVE = 9  # OptionType.EVOLVE — `area`+`index` locate the evolution card in hand
_OPT_ABILITY = 10  # OptionType.ABILITY — `area`+`index` locate the Pokémon whose Ability fires


def _first(cards: dict[int, dict], pred) -> int | None:
    """Lowest card id matching ``pred`` (deterministic), or None."""
    return next((cid for cid in sorted(cards) if pred(cards[cid])), None)


def build_probe_deck(target_id: int, cards: dict[int, dict], low_hp: bool = False,
                     search_fodder: bool = False) -> list[int]:
    """A legal 60-card deck stuffed with ``target_id`` so it's drawable enough to probe.

    ``low_hp`` seeds the *frailest* Basics instead of the sturdiest — for the attrition pass,
    where my Active is meant to be KO'd (stocking my discard with a Pokémon + Energy → ``recycle``
    targets, and ensuring the opponent has attached Energy → ``energy_denial`` targets).

    ``search_fodder`` adds a couple of *frail* Basics **and** a Supporter alongside the sturdy
    bench — so an HP-capped search ("≤70 HP") or a Supporter-fetch has a legal target. Only the
    stable pass uses it (no combat → the frail extras can't hurt heal/attrition probing).
    """
    tcard = cards.get(target_id, {})
    copies = 1 if tcard.get("aceSpec") else 4    # ≤4 same-name cards; ACE SPEC is capped at 1
    deck = [target_id] * copies
    # Basic Pokémon: a few *distinct* ones (4 copies each) so a bench can be fielded (for
    # gust/switch probing) and fetch effects have targets. Skip only if the target itself is a
    # Basic (it is the board). ≤4 same-name keeps every copy-count legal.
    if not (tcard.get("category") == "pokemon" and tcard.get("stage") == "basic"):
        hp_key = ((lambda c: (cards[c].get("hp", 0), c)) if low_hp        # frail → KO'd (attrition)
                  else (lambda c: (-cards[c].get("hp", 0), c)))           # sturdy → survives chip
        basics = sorted((c for c in cards if cards[c].get("category") == "pokemon"
                         and cards[c].get("stage") == "basic"), key=hp_key)
        for b in basics[:_BENCH_BASICS]:
            deck += [b] * 4
        if search_fodder:
            seeded = set(deck)
            frail = sorted((c for c in cards if cards[c].get("category") == "pokemon"
                            and cards[c].get("stage") == "basic" and c not in seeded),
                           key=lambda c: (cards[c].get("hp", 0), c))      # frailest → HP-capped fetch
            deck += [b for b in frail[:2] for _ in range(4)]
            sup = _first(cards, lambda c: c.get("category") == "supporter")
            if sup is not None and sup != target_id:
                deck += [sup] * 4                                         # a Supporter-fetch target
    energies = sorted(c for c in cards if cards[c].get("category") == "basic_energy")
    # Stable/chip: one Energy type is enough. Attrition (low_hp) spreads *all* basic Energy so the
    # diverse frail attackers can actually pay their costs and KO (a single type often can't).
    fill = energies if (low_hp and energies) else (energies[:1] or [None])
    i = 0
    while len(deck) < _DECK_SIZE:                    # basic energy is exempt from the 4-copy cap
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
    """Index into ``obs.select.option`` that activates ``target_id``'s Ability, or None.

    An ABILITY option points at a Pokémon in play via ``area`` (ACTIVE/BENCH) + ``index``
    (+ ``playerIndex``, defaulting to ``me`` since Abilities are always your own).
    """
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
    """Basic-first evolution line ending at ``target_id`` (e.g. ``[Dreepy, Drakloak, Dragapult]``).

    Walks ``evolvesFrom`` (a pre-evolution *name*) backwards, resolving each name to the
    lowest card id so reprints are deterministic. A Basic returns ``[target_id]``.
    ``data`` maps ``cardId -> {"name", "evolvesFrom"}`` (engine-sourced; lib-free here).
    """
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


def find_evolve_option(obs: dict, evolved_id: int, me: int = 0,
                       in_play_area: int | None = None) -> int | None:
    """Index into ``obs.select.option`` that evolves a field Pokémon into ``evolved_id``, or None.

    An EVOLVE option locates the evolution card in hand via ``area`` (HAND) + ``index``, and the
    Pokémon being evolved via ``inPlayArea`` + ``inPlayIndex``. Pass ``in_play_area`` to require
    a particular spot (the drive uses ACTIVE so the line climbs the Active, not a benched copy).
    """
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
    """Probe record ``{actor, logs, contexts}`` from a post-play observation.

    ``logs`` pass through faithfully (the classifier filters by player); ``contexts`` is the
    resulting select context — a sub-decision the play raised (e.g. a free damage-counter
    placement). Pure; tolerates missing logs/select.
    """
    sel = obs_after.get("select") or {}
    contexts = [sel["context"]] if "context" in sel else []
    return {"actor": actor, "logs": obs_after.get("logs") or [], "contexts": contexts}


# --- lib drive-shell (run-validated, not unit-tested; lazy `cg` import) ------------

_CTX_MAIN = 0       # SelectContext.MAIN — a fresh action choice (the card has resolved)
_SETUP_ACTIVE = 1   # SelectContext.SETUP_ACTIVE_POKEMON — place the target Active here
_SETUP_BENCH = 2    # SelectContext.SETUP_BENCH_POKEMON — seed the bench here
_OPT_END = 14       # OptionType.END — end my turn
_OPT_ATTACH = 8     # OptionType.ATTACH — manually attach a card to a Pokémon
_OPT_ATTACK = 13    # OptionType.ATTACK
_LOG_ATTACK = 15    # LogType.ATTACK — the attack event (record keeps from here: drops energize/draws)
_LOG_TURN_START = 2  # LogType.TURN_START — a turn boundary (capture must stop here)
_LOG_TURN_END = 3    # LogType.TURN_END
_AREA_HAND = 2      # AreaType.HAND
_AREA_ACTIVE = 4    # AreaType.ACTIVE
_AREA_BENCH = 5     # AreaType.BENCH
_CTX_REMOVE_DMG = 16  # SelectContext.REMOVE_DAMAGE_COUNTER
_CTX_HEAL = 17        # SelectContext.HEAL


def _attack_turn_logs(logs: list[dict]) -> list[dict]:
    """Slice ``logs`` to the attacking turn: from the first ATTACK up to the next turn boundary.

    Drops the pre-attack energize (before the ATTACK) *and* any later turn's re-energize ATTACH —
    the drive may attack across turns, and a subsequent turn's manual energy attach would
    otherwise read as a false ``energy_accel``. Pure; tolerates no-ATTACK / no-boundary logs.
    """
    s = next((i for i, l in enumerate(logs) if l.get("type") == _LOG_ATTACK), 0)
    e = next((j for j in range(s + 1, len(logs))
              if logs[j].get("type") in (_LOG_TURN_START, _LOG_TURN_END)), len(logs))
    return logs[s:e]


_ATTACK_DMG = None        # lazy {attackId: damage} cache (built once from the engine)
_ATTACK_ENERGIES = None   # lazy {cardId: cheapest attack's energy list}
_CARD_ENERGY = None       # lazy {cardId: EnergyType int} (a Pokémon's own type)
_ABILITY_MONS = None      # lazy set of cardIds that have ≥1 Ability (skill)
_ATTACK_COSTLIEST = None  # lazy {cardId: (attackId, energies)} — the priciest attack (effect-bearing)
_EVO_DATA = None          # lazy {cardId: {name, evolvesFrom, stage1, stage2}}


def _cg_on_path():
    import sys
    from pathlib import Path
    ms = str(Path(__file__).resolve().parents[2] / "my_submissions")
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
    """``{cardId: (attackId, energies)}`` for each card's *most expensive* attack (built once).

    Marquee effects — spread (Dragapult's Phantom Dive), heavy status — sit on the costliest
    attack, not the cheapest, so evolution probing energizes for and selects this one.
    """
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
    """Option index of the desired attack (by ``attackId``); None if not (yet) available.

    With ``want_attack`` set we hold out for that specific attack (the costliest/effect one) —
    returning None makes the drive bank more Energy rather than fire a cheap vanilla attack.
    """
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
    """Move past a decision we don't probe (setup / opponent / sub-step).

    During the setup bench step, take *all* offered Pokémon (build a board → enables
    gust/switch probing); otherwise minCount-first.
    """
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
    """Build the board so energy/heal effects have something to act on.

    Always tries to attach an Energy. If ``attack`` (only the opponent drives this), it also
    attacks: the *weakest* attack to **chip** slowly (heal targets, long games), or — with
    ``ko`` — the *strongest* to KO my frail Active fast (attrition: stock my discard +
    guarantee the opponent has Energy → recycle / energy_denial targets). (Run-validated.)
    """
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
            pick = max(positive) if ko else min(positive)   # KO fast vs chip slowly
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
    """Resolve forced sub-decisions from ``obs`` (a just-applied effect), accumulating the record.

    Returns ``(record, final_obs)`` so the caller can keep driving the same turn (e.g. attack
    after using an Ability). Stops at MAIN / match end / the opponent's turn.
    """
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


def probe_card(target_id: int, cards: dict[int, dict], *, me: int = 0,
               attack: bool = False, ko: bool = False, max_steps: int = 400) -> dict | None:
    """Drive a real game until ``me`` can play ``target_id``; return its probe record (or None).

    Builds a legal probe deck, advances setup and turns, and on the actor's MAIN turn plays
    the target and captures what it did. Three scenarios:
      * stable (default) — the game stays quiet (best for draw/search/gust/switch);
      * ``attack=True`` — the opponent *chips* my sturdy board (heal/damage targets), holding the
        target until my Active is damaged;
      * ``ko=True`` — attrition: the opponent *KOs* my frail Active (held until my discard is
        stocked), so a Pokémon + Energy hit my discard (→ ``recycle``) and the opponent has
        Energy attached (→ ``energy_denial``).
    Returns None if the card never became playable within ``max_steps`` — such cards fall to a
    curated override. The builder probes every scenario and unions the tags.
    """
    combat = attack or ko
    battle_start, battle_select, battle_finish = _engine()
    deck = build_probe_deck(target_id, cards, low_hp=ko, search_fodder=not combat)  # fodder: stable only
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
                    return _resolve_play(battle_select, obs, opt, me)
                obs = _develop(battle_select, obs, cards)                   # I build board, never attack
            else:
                obs = _develop(battle_select, obs, cards, attack=combat, ko=ko)  # opponent chips/KOs
        return None
    finally:
        battle_finish()


def probe_pokemon(target_id: int, cards: dict[int, dict], *, me: int = 0,
                  max_steps: int = 250) -> dict | None:
    """Drive a game to make ``target_id`` (a Pokémon) attack; return its probe record (or None).

    Places the target in the Active spot, attaches its attack's Energy each turn, and attacks
    once able — recording the attack's effect (damage / `status` / `spread`). Both benches are
    seeded so spread/status have targets. Stage 1/2 attackers (need their line) aren't reached.
    """
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
                obs = battle_select([o] if o is not None else [0])         # put the target Active
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
                    rec["logs"] = _attack_turn_logs(rec["logs"])          # this turn only (no energize leak)
                    return rec
                obs = _end_turn(battle_select, obs)
            else:
                obs = _end_turn(battle_select, obs)
        return None
    finally:
        battle_finish()


def probe_pokemon_ability(target_id: int, cards: dict[int, dict], *, me: int = 0,
                          max_steps: int = 160) -> dict | None:
    """Drive a game to activate ``target_id``'s Ability; return its probe record (or None).

    Places the target Active and attaches its *own-type* Energy each turn (fuel for
    energy-hungry Abilities), then activates the Ability the moment the engine offers it — the
    option only appears when the Ability is *usable*, so its presence means the precondition is
    met. Resolves the Ability's sub-decisions (reusing the play resolver). Passive Abilities
    never become an option → None. Basic mons only (Stage 1/2 need their line).
    """
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
                obs = battle_select([o] if o is not None else [0])         # put the target Active
            elif ctx != _CTX_MAIN:
                obs = _advance(battle_select, obs)                         # setup (benches) / sub-decision
            elif you == me:
                opt = find_ability_option(obs, target_id, me)
                if opt is not None:
                    return _resolve_play(battle_select, obs, opt, me)      # activate + record the Ability
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
    """Drive a game to evolve up to ``target_id`` (Stage 1/2), then capture its Ability + its
    *costliest* attack → ``spread`` / ``status`` / ``draw`` / ``energy_accel``. Record or None.

    Builds the full evolution line, places the Basic Active, evolves the Active one step per
    turn, banks the costliest attack's Energy, then (once) activates the Ability and fires the
    costliest attack — the one that carries the marquee effect (Dragapult's Phantom Dive →
    ``spread``). The free damage-counter sub-decision is resolved so its ``DAMAGE_COUNTER_ANY``
    context is recorded; the opponent benches the same line, so spread has targets. The attack
    record is trimmed to the ``ATTACK`` event so the energize setup doesn't leak in.
    """
    chain = evolution_chain(target_id, _evolution_data())
    if len(chain) < 2:
        return None                                   # a Basic — handled by probe_pokemon
    costliest = _card_attack_costliest().get(target_id)
    energies = costliest[1] if costliest else [0]
    want_attack = costliest[0] if costliest else None
    battle_start, battle_select, battle_finish = _engine()
    deck = build_evolution_deck(chain, energies)
    obs, start = battle_start(deck, _bench_deck(cards))   # opponent fields a Bench → spread targets
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
                    for stage_id in reversed(chain[1:]):                   # evolve the Active up the line
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
                if atk is not None:                                        # fire the costliest (effect) attack
                    obs = battle_select([atk])
                    r, obs = _resolve_from(battle_select, obs, me)         # resolve the spread placement
                    logs += _attack_turn_logs(r["logs"])                   # this turn only (no energize leak)
                    contexts += r["contexts"]
                    break
                if not cur.get("energyAttached"):
                    ai = _find_attach_energy(obs, cards)
                    if ai is not None:
                        obs = battle_select([ai]); continue                # bank Energy for the costly attack
                obs = _end_turn(battle_select, obs)
            else:
                obs = _end_turn(battle_select, obs)
    finally:
        battle_finish()
    return {"actor": me, "logs": logs, "contexts": contexts} if (logs or contexts) else None
