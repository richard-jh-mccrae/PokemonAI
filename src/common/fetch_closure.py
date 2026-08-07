"""Fetch-closure — the tutor / search graph and its clause predicates (WP7, ADR-0065).

Pure functions over the card REPRESENTATION only: ``card_effects.json`` FETCH clauses + ``CardStat``,
NEVER a card-text parse. One implementation, so every valuation shadow reads the same closure.

The clause predicate is zone-agnostic, but the graph WALKS here cover only the ``zone: deck`` leg — a
shuffled card lands in the DECK, and the recycle leg lives with the slot closure.

Accessors instead of a Pilot: ``stat_of(cid) -> CardStat | None``, ``clauses_of(cid) -> iterable[dict]``.

Fail direction (ADR-0064): every predicate is an ENDORSER — bad input yields False / 0 (an
under-count), never a raise and never a false positive that unlocks a play.
"""
from __future__ import annotations

from typing import NamedTuple

# The REACH scope: FETCH-clause target classes naming a POKÉMON. Each narrow class is a strict SUBSET
# of `pokemon`, so admitting one adds no claim the scope could not already make.
FETCH_POKEMON_TARGETS = frozenset({"pokemon", "basic_pokemon", "mega", "evolution",
                                   "stage1", "stage2", "tera", "pokemon_ex"})

# The non-Pokémon TRAINER classes a fetch can name — each a strict subset of `trainer`.
FETCH_TRAINER_TARGETS = frozenset({"item", "tool", "stadium"})

# Classes resolving for DEADNESS but NEVER for REACH, in ONE store. An UNDER-count, this module's
# safe direction; un-gating either owes ADR-0073's measurement.
FETCH_DEADNESS_ONLY_TARGETS = frozenset({"supporter", "any"})

# The DEADNESS scope (ADR-0073), deliberately WIDER than reach: `all(target provably gone)` only gets
# HARDER, so over-inclusion suppresses a claim but never fabricates one. Gated by test_fetch_closure.
FETCH_DEADNESS_TARGETS = (FETCH_POKEMON_TARGETS | FETCH_TRAINER_TARGETS
                          | FETCH_DEADNESS_ONLY_TARGETS
                          | frozenset({"trainer", "energy", "basic_energy"}))


#: Clause fields that make a fetch something OTHER than an unconditional, decidable whole-deck
#: search — see :func:`fetch_is_unconditional`.
_CONDITIONAL_FETCH_FIELDS = ("trigger", "dig", "condition", "name_family")


def fetch_is_unconditional(clause: dict) -> bool:
    """Is this FETCH clause the unconditional, decidable whole-deck search every REACH consumer assumes
    — *"play the card, get the target"*? DEADNESS deliberately does not ask (ADR-0073)."""
    return not any(clause.get(f) for f in _CONDITIONAL_FETCH_FIELDS)


def _pokemon_body_matches(clause: dict, stat) -> bool:
    """The per-BODY predicates every Pokémon target class shares. Applied UNIFORMLY, not per class:
    each is a property of the body fetched, so a per-class spelling fails OPEN on a new pairing."""
    if clause.get("no_rule_box") and getattr(stat, "is_ex_body", False):
        return False
    if clause.get("no_ability") and getattr(stat, "hasAbility", False):
        return False
    hp_max = clause.get("hp_max")
    return hp_max is None or getattr(stat, "hp", 0) <= hp_max


def fetch_target_matches(clause: dict, stat, *, deadness: bool = False) -> bool:
    """Does a card with ``stat`` match a FETCH ``clause``'s target class? ``energy_type`` binds ENERGY
    targets only. ``deadness=True`` asks the OPPOSITE question; the default is the safe reading."""
    if stat is None:
        return False
    if not deadness and not fetch_is_unconditional(clause):
        return False              # not an unconditional, decidable whole-deck search — never an edge
    target = clause.get("target")
    etype = clause.get("energy_type")
    if target == "any":
        # DEADNESS-ONLY: it names no class, and reach's endorsement set is made of classes. Gated
        # HERE, so the guarantee does not rest on one caller remembering to apply a filter.
        return deadness
    if target == "basic_energy":
        return stat.is_basic_energy and (etype is None or getattr(stat, "energyType", None) == etype)
    if target == "energy":
        return stat.is_energy and (etype is None or getattr(stat, "energyType", None) == etype)
    if target == "supporter":
        return deadness and bool(getattr(stat, "is_supporter", False))   # deadness-only, see above
    if target == "item":
        return bool(getattr(stat, "is_item", False))
    if target == "tool":
        return bool(getattr(stat, "is_tool", False))
    if target == "stadium":
        return bool(getattr(stat, "is_stadium", False))
    if target == "trainer":
        return not stat.is_pokemon and not stat.is_energy
    if target not in FETCH_POKEMON_TARGETS:
        return False
    # ── the Pokémon classes: the class question, then the shared per-body predicates ──────────────
    if not stat.is_pokemon:
        return False
    if target == "mega":
        if not getattr(stat, "megaEx", False):
            return False
    elif target == "evolution":
        if not getattr(stat, "evolvesFrom", None):
            return False
    elif target == "basic_pokemon":
        if getattr(stat, "evolvesFrom", None):
            return False
    elif target == "stage1":
        if getattr(stat, "stage", None) != "stage1":
            return False
    elif target == "stage2":
        if getattr(stat, "stage", None) != "stage2":
            return False
    elif target == "tera":
        if not getattr(stat, "tera", False):
            return False
    elif target == "pokemon_ex":
        if not getattr(stat, "is_ex_body", False):
            return False
    return _pokemon_body_matches(clause, stat)


#: ``relation`` is ``"single"`` / ``"union"`` / ``"conjunction"``; ``cap`` is how many cards the whole
#: PLAY delivers (a union's shared budget, or 1 per leg for a conjunction). See :func:`reveal_legs`.
RevealLegs = NamedTuple("RevealLegs", [("relation", str), ("legs", tuple), ("cap", int)])


def reveal_legs(clauses) -> RevealLegs:
    """How a card's revealing clauses COMBINE — the ONE reader of the multi-leg relation, so the two
    reveal nodes cannot each guess it. Raises ``ValueError``; the CALLER owns the refusal sentence."""
    from common.snapshot_coverage import REVEALING_CLAUSES
    legs = tuple(c for c in (clauses or ()) if c.get("kind") in REVEALING_CLAUSES)
    if not legs:
        raise ValueError("no `draw`/`fetch` clause, so this option is a point transition rather "
                         "than a reveal node")
    if len(legs) == 1:            # a lone reach-gated leg is deliberately NOT refused: with no other
        return RevealLegs("single", legs, _leg_cap(legs[0]))   # leg, no partial answer is possible
    gated = sorted({c.get("target") for c in legs
                    if c.get("target") in FETCH_DEADNESS_ONLY_TARGETS})
    if gated:
        raise ValueError(
            f"a leg targets {gated} — reach-gated classes that match nothing structurally, so "
            f"enumerating the other legs would model part of a card while reporting completeness")
    flagged = [bool(c.get("choice")) for c in legs]
    if any(flagged) and not all(flagged):
        raise ValueError(
            f"`choice` is declared on {sum(flagged)} of {len(legs)} revealing legs — neither a "
            f"union nor a conjunction can be read from a half-declared relation")
    if not any(flagged):
        return RevealLegs("conjunction", legs, 1)
    caps = {_leg_cap(c) for c in legs}
    if len(caps) > 1:
        raise ValueError(
            f"an exclusive either-or: the `choice` legs carry different caps {sorted(caps)}, so the "
            f"branches have separate budgets and no single shared cap to enumerate over")
    return RevealLegs("union", legs, caps.pop())


def multiset_classes(pool: dict, m: int) -> list:
    """The ``m``-card deliveries a ``{card id: copies}`` pool can produce, as sorted id tuples. A
    MULTISET enumerator, and exactly ``min(m, total)`` cards — taking fewer into HAND is DOMINATED."""
    total = sum(pool.values())
    take = min(int(m), total)
    if take < 1 or not pool:
        return []
    ids = sorted(pool)
    out: list = []

    def walk(i: int, left: int, acc: tuple) -> None:
        if left == 0:
            out.append(acc)
            return
        if i >= len(ids):
            return                                  # this branch cannot fill the delivery
        cid = ids[i]
        for count in range(min(int(pool[cid]), left), -1, -1):
            walk(i + 1, left - count, acc + (cid,) * count)

    walk(0, take, ())
    return sorted(out)


def _leg_cap(clause: dict) -> int:
    """How many cards ONE leg delivers. Absent ``amount`` is 1; ``"all"`` reads as 0 rather than being
    guessed, because only the caller has a real pool to resolve it against."""
    amount = clause.get("amount")
    if amount is None:
        return 1
    return amount if isinstance(amount, int) and not isinstance(amount, bool) else 0


def _deck_fetch_clauses(clauses_of, cid):
    """The card's ``zone: deck`` FETCH clauses (the deck-search leg of the graph). () when unknown."""
    return [cl for cl in (clauses_of(cid) if clauses_of else ())
            if cl.get("kind") == "fetch" and cl.get("zone") == "deck"]


def reaccess_outs(cid, counts: dict, stat_of, clauses_of) -> int:
    """Deck copies that re-access ``cid`` once it is shuffled back in — its own copies plus every
    deck-search tutor reaching it. NOT a sound bound; it mostly UNDER-counts, which is the safe way."""
    return class_reaccess_outs((cid,), counts, stat_of, clauses_of)


def class_reaccess_outs(cids, counts: dict, stat_of, clauses_of) -> int:
    """Deck copies that re-supply ANY of the classes ``cids`` — the SET generalization of
    `reaccess_outs`. Each tutor counts ONCE: summing per class would double-count a multi-class one."""
    known = {}
    for cid in cids:
        st = stat_of(cid) if cid is not None else None
        if st is not None:
            known[cid] = st
    if not known:
        return 0
    outs = sum(counts.get(cid, 0) for cid in known)
    for tid, n in counts.items():
        if n <= 0 or tid in known:
            continue
        clauses = _deck_fetch_clauses(clauses_of, tid)
        if any(fetch_target_matches(cl, st) for cl in clauses for st in known.values()):
            outs += n
    return outs


def fetch_reaches_pokemon(target_id, cid: int, counts: dict, stat_of, clauses_of) -> bool:
    """Can card ``cid``'s ``zone: deck`` FETCH clauses pull the Pokémon ``target_id``, still in
    ``counts``? Through the shared predicate, so per-body restrictions are never lost."""
    if counts.get(target_id, 0) <= 0:
        return False
    tst = stat_of(target_id) if target_id is not None else None
    if tst is None or not tst.is_pokemon:
        return False
    return any(fetch_target_matches(cl, tst) for cl in _deck_fetch_clauses(clauses_of, cid))
