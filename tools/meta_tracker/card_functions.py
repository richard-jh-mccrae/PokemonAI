"""Behavioral function tags for cards — pure & lib-free (see docs/card-functions.md).

What a card *does*, as a small set of string tags, from two sources:
  * an engine **probe** record — what the card did when played, captured by the
    lib-using ``probe_cards.py`` harness (its schema mirrors the engine's ``Log`` /
    ``SelectContext``; codes are mirrored locally below to keep this module lib-free);
  * curated **overrides** — a thin escape hatch for what the probe can't reach.

Only *behavioral* function is tagged (draw/search/heal/poison/spread/…). **Structural** facts
(ex/Mega-ex → prizes, trainer subtype, ACE SPEC) are deliberately NOT tagged: the runtime reads
them straight off the engine's ``CardData`` (``ex``/``megaEx``/``cardType``/``aceSpec``), so
duplicating them here would only bloat the table (revises ADR-0006).
"""
from __future__ import annotations

# Engine enum codes mirrored locally so this module stays lib-free (cg/api.py).
_LOG_DRAW = 4                  # LogType.DRAW
_LOG_MOVE_CARD = 6             # LogType.MOVE_CARD
_LOG_MOVE_REVERSE = 7          # LogType.MOVE_CARD_REVERSE (an opponent's hidden card moved)
_LOG_SWITCH = 8                # LogType.SWITCH (an Active Pokémon was swapped)
_LOG_ATTACH = 11               # LogType.ATTACH (a card attached to a Pokémon)
_LOG_HP_CHANGE = 16            # LogType.HP_CHANGE (value>0 & not a damage counter = heal)
# Each Special Condition → its own tag (purpose-specific, not a vague `status`): poison/burn are
# chip-damage attrition; sleep/paralyze lock the Active out of attacking/retreating; confuse deters.
_CONDITION_TAG = {17: "poison", 18: "burn", 19: "sleep", 20: "paralyze", 21: "confuse"}
_AREA_DECK = 1                 # AreaType.DECK
_AREA_HAND = 2                 # AreaType.HAND
_AREA_DISCARD = 3              # AreaType.DISCARD
_AREA_ACTIVE = 4               # AreaType.ACTIVE
_AREA_BENCH = 5                # AreaType.BENCH
_AREA_ENERGY = 8               # AreaType.ENERGY (Energy attached to a Pokémon)
_AREA_LOOK = 12                # AreaType.LOOKING (cards being looked at)
_INTO_PLAY = frozenset((2, 4, 5))   # HAND / ACTIVE / BENCH — destinations of a fetch
_CTX_DAMAGE_COUNTER_ANY = 14   # SelectContext.DAMAGE_COUNTER_ANY


def classify_functions(card: dict, *, probe: dict | None = None,
                       overrides: list[str] | None = None) -> list[str]:
    """Return the sorted *behavioral* function tags for one card. Pure; never raises on sparse
    input. Structural facts (ex / trainer subtype / ACE SPEC) are intentionally *not* tagged —
    the runtime reads them off ``CardData`` directly (see the module docstring)."""
    tags: set[str] = set()

    # --- Behavioral tags (from the engine probe record) ---
    if probe:
        actor = probe.get("actor")
        for lg in probe.get("logs") or []:
            t = lg.get("type")
            mine = lg.get("playerIndex") == actor
            if t == _LOG_SWITCH:
                tags.add("switch" if mine else "gust")   # my Active out vs forcing the opponent's
                continue
            cond = _CONDITION_TAG.get(t)
            if cond and not lg.get("isRecover"):
                tags.add(cond)               # the specific Special Condition inflicted (poison/burn/…)
                continue
            if not mine:                 # opponent-side moves my card *forced* during its resolution
                if t in (_LOG_MOVE_CARD, _LOG_MOVE_REVERSE):
                    frm, to = lg.get("fromArea"), lg.get("toArea")
                    if frm == _AREA_HAND and to in (_AREA_DECK, _AREA_DISCARD):
                        tags.add("hand_disruption")   # shuffled/discarded the opponent's hand (Iono/Judge)
                    elif frm == _AREA_ENERGY and to == _AREA_DISCARD:
                        tags.add("energy_denial")     # knocked an Energy off the opponent (Hammer)
                continue                 # other opponent events aren't this card's own function
            if t == _LOG_DRAW:
                tags.add("draw")
            elif t == _LOG_MOVE_CARD:
                frm, to = lg.get("fromArea"), lg.get("toArea")
                if _AREA_LOOK in (frm, to):
                    tags.add("dig")          # looked at / reordered the deck top (or bottom)
                if frm == _AREA_DECK and to in (_AREA_HAND, _AREA_BENCH, _AREA_ACTIVE):
                    tags.add("search")       # tutored a specific card *straight* out of the deck
                elif frm == _AREA_LOOK and to == _AREA_HAND:
                    tags.add("draw")         # took a card from a looked-at set (Drakloak) = dig+draw, not a tutor
                elif frm == _AREA_DISCARD and to in _INTO_PLAY:
                    tags.add("recycle")      # pulled a card back out of my discard (Night Stretcher)
            elif t == _LOG_ATTACH and card.get("category") != "tool":
                tags.add("energy_accel")     # a non-Tool card attaching = put Energy into play
            elif t == _LOG_HP_CHANGE and (lg.get("value") or 0) > 0 and not lg.get("putDamageCounter"):
                tags.add("heal")             # my Pokémon's HP went up = removed damage
        if _CTX_DAMAGE_COUNTER_ANY in (probe.get("contexts") or []):
            tags.add("spread")           # free damage-counter placement (the Dragapult class)

    # --- Curated overrides (escape hatch: union, for what the probe can't reach) ---
    tags |= set(overrides or [])

    return sorted(tags)


def build_function_table(cards: dict[int, dict], probes: dict[int, dict] | None = None,
                         overrides: dict[int, list[str]] | None = None) -> dict[int, list[str]]:
    """Map ``classify_functions`` over the pool → ``{cardId: tags}`` (untagged cards omitted)."""
    probes = probes or {}
    overrides = overrides or {}
    table: dict[int, list[str]] = {}
    for cid, card in cards.items():
        tags = classify_functions(card, probe=probes.get(cid), overrides=overrides.get(cid))
        if tags:
            table[cid] = tags
    return table


def accumulate_tables(new: dict[int, list[str]],
                      prior: dict[int, list[str]]) -> dict[int, list[str]]:
    """Union this run's table with a prior run's — **monotonic**: a once-observed tag is never
    dropped, so successive (stochastic) probe builds only *add* coverage for the rng-gated tags
    (recycle/energy_denial/heal/…). Sorted; cards with no tags omitted. (To discard stale tags
    after a classify-rule change, rebuild ``--fresh`` instead of accumulating.)"""
    out: dict[int, set] = {cid: set(tags) for cid, tags in prior.items()}
    for cid, tags in new.items():
        out.setdefault(cid, set()).update(tags)
    return {cid: sorted(tags) for cid, tags in out.items() if tags}
