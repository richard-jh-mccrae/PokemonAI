"""Fetch-closure — the tutor / search graph and its clause predicates (WP7, ADR-0065).

The oracle's GRAPH leg, lifted out of the Pilot into pure, Pilot-independent functions over the card
REPRESENTATION only: ``card_effects.json`` FETCH clauses (ADR-0032) + ``CardStat`` — **never a card-text
parse** (the Round-11 ruling). One implementation, called by both the gamble gain side
(`planner._fetch_reaches_pokemon` / `_card_reaccess_outs`) and the card-worth keep-cost
(`card_worth` via the Pilot) so the four valuation shadows read the SAME closure by construction.

Scope: the clause predicate (`fetch_target_matches`) is zone-agnostic — it matches a recycler's
``zone: discard`` clause as readily as a deck search — but the graph walks here (`reaccess_outs`,
`fetch_reaches_pokemon`) deliberately cover only the ``zone: deck`` leg: a shuffled card lands in the
DECK, and the gamble's recycle/discard leg lives with the slot closure (`planner._fetch_reaches_slot`).

Each function takes small accessor callables instead of a Pilot:
  * ``stat_of(cid) -> CardStat | None`` — the card's stat row (``pilot.stats.get``)
  * ``clauses_of(cid) -> iterable[dict]`` — its effect clauses (``pilot.effects.clauses``)

Fail direction (grader safety, ADR-0064): every predicate is an ENDORSER — bad/absent input yields
``False`` / ``0`` (under-count), never a raise and never a false positive that unlocks a play.
"""
from __future__ import annotations

# The FETCH-clause target classes that name a POKÉMON (the scope the retired tag-keyed
# ``_FETCH_FILTERS`` covered: bench_fill / tutor_mega / tutor_pokemon / rush_evolve).
FETCH_POKEMON_TARGETS = frozenset({"pokemon", "basic_pokemon", "mega", "evolution"})


def fetch_target_matches(clause: dict, stat) -> bool:
    """True iff a card with ``stat`` matches a FETCH ``clause``'s target class (``card_effects.json``,
    ADR-0032) — the ONE predicate that REPLACED the tag-keyed ``_FETCH_FILTERS``. Targets:
    basic_energy / energy (± ``energy_type`` lock) · mega (Mega ex) · evolution (``evolvesFrom`` set,
    ± ``no_ability``) · pokemon / basic_pokemon (± ``no_rule_box``, ``hp_max``) · trainer (any
    non-Pokémon non-Energy card: Item / Supporter / Tool / Stadium — Team Rocket's Petrel; the
    tutor-chain graph leg, seam C).

    NOTE: ``energy_type`` on a POKÉMON target (Fighting Gong's "Basic {F} Pokémon") is NOT resolvable
    from ``CardStat`` (no Pokémon-type field), so it is applied only to ENERGY targets — a Pokémon
    target over-includes on type (fail-open; never false-suppresses a whiff; exact for a mono-type deck).

    A clause carrying ``trigger`` (a play-gated ability, Meowth ex's on-bench fetch) or ``dig``
    (a top-N look, Pokégear's dig-7) is REJECTED outright: neither is the unconditional whole-deck
    search the closure's deterministic-interior-hop model assumes (spec §thesis), so counting one as
    an out would over-claim. Today both carriers are ``target: supporter`` clauses that no branch
    below matches anyway — this guard makes that rejection load-bearing instead of accidental.
    """
    if stat is None:
        return False
    if clause.get("trigger") or clause.get("dig"):
        return False                       # not an unconditional whole-deck search — never a closure edge
    target = clause.get("target")
    etype = clause.get("energy_type")
    if target == "basic_energy":
        return stat.is_basic_energy and (etype is None or getattr(stat, "energyType", None) == etype)
    if target == "energy":
        return stat.is_energy and (etype is None or getattr(stat, "energyType", None) == etype)
    if target == "trainer":
        return not stat.is_pokemon and not stat.is_energy
    if target == "mega":
        return bool(getattr(stat, "megaEx", False))
    if target == "evolution":
        return (bool(getattr(stat, "evolvesFrom", None))
                and (not clause.get("no_ability") or not getattr(stat, "hasAbility", False)))
    if target in ("pokemon", "basic_pokemon"):
        if not stat.is_pokemon:
            return False
        if target == "basic_pokemon" and getattr(stat, "evolvesFrom", None):
            return False
        if clause.get("no_rule_box") and getattr(stat, "is_ex_body", False):
            return False
        hp_max = clause.get("hp_max")
        return hp_max is None or getattr(stat, "hp", 0) <= hp_max
    return False


def _deck_fetch_clauses(clauses_of, cid):
    """The card's ``zone: deck`` FETCH clauses (the deck-search leg of the graph). () when unknown."""
    return [cl for cl in (clauses_of(cid) if clauses_of else ())
            if cl.get("kind") == "fetch" and cl.get("zone") == "deck"]


def reaccess_outs(cid, counts: dict, stat_of, clauses_of) -> int:
    """The copies in the DECK that re-access card ``cid`` once it is shuffled back in — its own deck
    copies PLUS every deck-search tutor whose FETCH clause reaches it (`fetch_target_matches`: Ultra
    Ball a Pokémon, Energy Search an energy, Fighting Gong a {F} Basic, Mega Signal a Mega ex …). The
    gamble's gain-side closure pointed BACKWARDS — the same predicate asked "can I get this card back?"
    A shuffled card lands in the DECK, so only deck re-access counts (no discard). 0 for an unknown
    card. MOSTLY errs by under-counting (a lower re-access → a higher, safer keep-cost) — held
    tutors that shuffle in with the card, and the discard leg, are never counted. Three small
    over-counting channels are accepted: a type-locked POKÉMON fetch over-includes off-type Basics
    (the `fetch_target_matches` NOTE), tutor play-COSTS are not charged (an Ultra Ball counts even
    when its discard-2 might be unpayable), and Supporter tutors count without the one-per-turn
    slot. Each is per-card small and next-turn-horizon plausible; none is a sound bound."""
    return class_reaccess_outs((cid,), counts, stat_of, clauses_of)


def class_reaccess_outs(cids, counts: dict, stat_of, clauses_of) -> int:
    """The copies in the DECK that re-supply ANY of the card classes ``cids`` — the SET
    generalization of `reaccess_outs` (the keep-value v2 slot-RESUPPLY leg, ADR-0065): a needs SLOT
    is filled by a class of cards, so its re-supply outs are the own deck copies of every KNOWN
    class plus every deck-search tutor whose FETCH clause reaches at least one of them, each tutor
    counted ONCE — summing per-class `reaccess_outs` would double-count an Ultra Ball that reaches
    two of the slot's Pokémon classes. Unknown classes contribute nothing (the endorser fail
    direction); a tutor that is itself a member class counts as own copies, never twice. The same
    accepted over-counting channels as `reaccess_outs`, none a sound bound."""
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
    """True iff card ``cid``'s ``zone: deck`` FETCH clauses can pull the Pokémon ``target_id`` (still in
    ``counts``) — via the shared `fetch_target_matches` predicate, so Poké Pad's ``no_rule_box`` never
    fetches a Rule-Box Mega ex (the parametric fact the generic ``tutor_pokemon`` tag can't carry)."""
    if counts.get(target_id, 0) <= 0:
        return False
    tst = stat_of(target_id) if target_id is not None else None
    if tst is None or not tst.is_pokemon:
        return False
    return any(fetch_target_matches(cl, tst) for cl in _deck_fetch_clauses(clauses_of, cid))
