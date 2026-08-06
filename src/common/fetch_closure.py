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

from typing import NamedTuple

# The FETCH-clause target classes that name a POKÉMON (the scope the retired tag-keyed
# ``_FETCH_FILTERS`` covered: bench_fill / tutor_mega / tutor_pokemon / rush_evolve). This is the
# REACH scope — the classes the closure graph and the doctrine's endorser set range over.
#
# Issue #301 added the four narrower Pokémon classes the compendium's fetch family needs:
# ``stage1`` (Hyper Aroma), ``stage2`` (Dawn), ``tera`` (Tera Orb) and ``pokemon_ex`` (Cyrano). Each
# names a strict SUBSET of the ``pokemon`` class already here, so widening the reach scope with them
# adds no claim the scope could not already make about the same body — it only lets the compendium
# state which bodies a card actually hunts instead of over-stating them as "a Pokémon".
FETCH_POKEMON_TARGETS = frozenset({"pokemon", "basic_pokemon", "mega", "evolution",
                                   "stage1", "stage2", "tera", "pokemon_ex"})

# The non-Pokémon TRAINER classes a fetch can name (Issue #301: Secret Box searches for an Item, a
# Pokémon Tool and a Stadium). Each is a strict subset of the ``trainer`` class that has been
# reach-eligible since seam C, so their admission narrows what the compendium claims rather than
# widening it.
FETCH_TRAINER_TARGETS = frozenset({"item", "tool", "stadium"})

# The target classes that resolve for DEADNESS but never for REACH. One store, so "which classes are
# gated?" has a single answer that both the predicate and its tests read:
#
# * ``supporter`` — ADR-0073's gate. Reading it for reach would make a plain Supporter search a
#   closure edge and move the out-count, which that ADR says is a deliberate, MEASURED change. Issue
#   #301 made the gate load-bearing (Secret Box carries a plain Supporter search, 2 copies).
# * ``any`` — it names no class at all, so `_search_deck_set` (*"the deck cards this search can be
#   RELIED ON to pull, BY CLASS"*) would have to mean something else to hold it. Both carriers
#   (Explorer's Guidance, Hassel) are ``dig`` clauses reach rejects anyway; gating it here keeps the
#   guarantee from resting on which cards happen to exist, exactly as the ``supporter`` gate does.
#
# Both are UNDER-counts, which is this module's stated safe direction.
FETCH_DEADNESS_ONLY_TARGETS = frozenset({"supporter", "any"})

# Every ``zone: deck`` FETCH target class — the DEADNESS scope (ADR-0073). Wider than the reach scope
# on purpose: deadness is ``all(target provably gone)``, which a wider set only makes HARDER to
# satisfy, so over-inclusion can suppress a claim but never fabricate one. A class missing from here
# is a card that can never be read as dead, which is exactly the issue-#164 hole (Pokégear 3.0,
# Energy Search / Pro, Fighting Gong, Hilda, Team Rocket's Petrel). Pinned by a coverage gate over
# the whole committed compendium (`test_fetch_closure.py`) — not merely over the shipped decks, which
# is what Issue #301's 26 at-once entries would have walked straight past — so a new fetch card fails
# a test rather than going silently invisible.
FETCH_DEADNESS_TARGETS = (FETCH_POKEMON_TARGETS | FETCH_TRAINER_TARGETS
                          | FETCH_DEADNESS_ONLY_TARGETS
                          | frozenset({"trainer", "energy", "basic_energy"}))


#: Clause fields that make a fetch something OTHER than an unconditional, decidable whole-deck
#: search — see :func:`fetch_is_unconditional`.
_CONDITIONAL_FETCH_FIELDS = ("trigger", "dig", "condition", "name_family")


def fetch_is_unconditional(clause: dict) -> bool:
    """Is this FETCH clause the unconditional, decidable whole-deck search every REACH consumer's
    model assumes — *"play the card, get the target"*?

    False when the clause carries ``trigger`` (a play-gated Ability, Meowth ex's on-bench grab),
    ``dig`` (a top-N look that may MISS a card still in the deck, Pokégear's 7), ``condition`` (a
    board gate — Call Bell's going-second-turn-1, Hassel's post-KO) or ``name_family`` (a restriction
    the closure records but cannot decide; see :func:`fetch_target_matches`).

    Lifted out of `fetch_target_matches` so the FOUR reach-side readers ask one question rather than
    each re-spelling the guard: this predicate, the planner's slot and Supporter-tutor legs, and the
    Attach Budget's hand-yield. They are the sites that turn "this card can find X" into a claim the
    agent acts on, so a gate one of them forgets is a fabricated out — the one direction this module
    forbids. Deadness deliberately does NOT ask (ADR-0073): a gate cannot put cards back in the deck,
    so ignoring it only widens the "is anything left?" set."""
    return not any(clause.get(f) for f in _CONDITIONAL_FETCH_FIELDS)


def _pokemon_body_matches(clause: dict, stat) -> bool:
    """The per-BODY predicates every Pokémon target class shares: ``no_rule_box`` (Poké Pad excludes
    a Rule-Box body), ``hp_max`` (Buddy-Buddy Poffin's ≤70) and ``no_ability`` (Salvatore's
    ability-less evolution).

    Applied uniformly rather than per class, because each is a property of the BODY being fetched,
    not of the class that names it: a ``mega``/``stage1``/``tera`` clause that grew an HP ceiling
    would otherwise silently ignore it, which is the fail-OPEN direction. No committed clause pairs
    one of these with a class other than the two that carried them first, so this is exactness ahead
    of need, not a behaviour change."""
    if clause.get("no_rule_box") and getattr(stat, "is_ex_body", False):
        return False
    if clause.get("no_ability") and getattr(stat, "hasAbility", False):
        return False
    hp_max = clause.get("hp_max")
    return hp_max is None or getattr(stat, "hp", 0) <= hp_max


def fetch_target_matches(clause: dict, stat, *, deadness: bool = False) -> bool:
    """True iff a card with ``stat`` matches a FETCH ``clause``'s target class (``card_effects.json``,
    ADR-0032) — the ONE predicate that REPLACED the tag-keyed ``_FETCH_FILTERS``. Targets:
    basic_energy / energy (± ``energy_type`` lock) · mega (Mega ex) · evolution (``evolvesFrom`` set)
    · pokemon / basic_pokemon · stage1 / stage2 (the printed stage) · tera · pokemon_ex · supporter
    (Pokégear 3.0, Meowth ex) · item / tool / stadium (Secret Box, Colress's Tenacity) · trainer (any
    non-Pokémon non-Energy card — Team Rocket's Petrel; the tutor-chain graph leg, seam C) · any
    (Explorer's Guidance, Hassel: a dig with no class restriction at all). Every Pokémon class
    additionally honours the per-body predicates ``no_rule_box`` / ``hp_max`` / ``no_ability``
    (`_pokemon_body_matches`).

    Two classes are DEADNESS-ONLY (:data:`FETCH_DEADNESS_ONLY_TARGETS`), so REACH is unchanged by
    ADR-0073 — provably, not just in practice. Both branches exist because the deadness reading must
    still resolve the class, and both refuse for reach:

    * ``supporter`` — the gate used to be inert (both carriers were ``dig``/``trigger`` clauses);
      **Issue #301 made it load-bearing**, since Secret Box now carries a PLAIN ``target: supporter``
      deck search, 2 copies across our decks. It stays gated, and that is a deliberate under-count:
      ADR-0073 says un-gating it is *"a deliberate change to the out-count (ADR-0065's epistemic),
      made with a measurement"*, and a Supporter out additionally ignores the one-per-turn slot the
      closure has no reading of. (The class is not *unreachable*: the wider ``trainer`` class,
      reach-eligible since seam C, already matches a Supporter — so this gate bounds what a
      supporter-SPECIFIC clause claims, not what the graph can see.)
    * ``any`` — it names no class, and reach's endorsement set is made of classes.

    Under-counting outs is this module's stated safe direction; the measurements that would un-gate
    either are separate, ruled changes.

    NOTE: ``energy_type`` on a POKÉMON target (Fighting Gong's "Basic {F} Pokémon", Canari's {L}) is
    deliberately applied only to ENERGY targets — a Pokémon target over-includes on type (fail-open;
    never false-suppresses a whiff; exact for a mono-type deck). ``CardStat.energyType`` *is*
    populated for a Pokémon body, so tightening this is decidable; it is not done here because it
    NARROWS the deadness set (the direction that can fabricate a deadness claim) on a live shipped
    clause, which owes its own measurement rather than riding a compendium-population issue.

    A clause carrying ``trigger`` (a play-gated ability, Meowth ex's on-bench fetch), ``dig`` (a
    top-N look, Pokégear's dig-7) or ``condition`` (a board gate — Call Bell's going-second-turn-1,
    Hassel's post-KO) is REJECTED outright: none is the unconditional whole-deck search the closure's
    deterministic-interior-hop model assumes (spec §thesis), so counting one as an out would
    over-claim.

    ``name_family`` (Hop's Bag's "Basic **Hop's** Pokémon") is rejected the same way, and for a
    sharper reason: the field records a restriction the closure cannot DECIDE. Issue #306 shipped
    `card_text.name_in_family`, a normalised prefix test over a KNOWN holder name, but the piece this
    would need is a build-time index over the pool keyed by family, baked into the clause so
    `deck_odds` can count members without a runtime name walk (Issue #301, cross-posting Issue #306).
    Ignoring the field instead would read Hop's Bag as fetching ANY Basic — a fabricated out on every
    Basic in the deck. Whoever revisits it starts from `name_in_family`, never a second matcher
    (ADR-0087: a hand-built second key is how the two sides of a diff come to share a bug).

    ``deadness=True`` (ADR-0073) asks the OPPOSITE question of the same clause row and is the ONE
    reading that skips those rejections. Reach is optimistic — *"can this card get me X back?"* — and
    a dig may MISS a card still in the deck, so it is no guarantee. Deadness is pessimistic — *"is
    anything left for this card to find?"* — and zero targets in the deck means the dig PROVABLY
    whiffs. A gate cannot put cards back in the deck and an undecidable name restriction only NARROWS
    what a card may find, so ignoring both in the deadness reading widens the set — and a wider set
    makes ``all(gone)`` harder, which can suppress a claim but never invent one. The default is the
    safe reading: a caller who forgets the flag gets a missed deadness claim (the agent plays a dead
    card, visible in a score-diff), never an inflated out-count (unsound, and invisible without a
    targeted test). Exactly one caller passes it — the doctrine's ``_fetch_deadness_set``.
    """
    if stat is None:
        return False
    if not deadness and not fetch_is_unconditional(clause):
        return False              # not an unconditional, decidable whole-deck search — never an edge
    target = clause.get("target")
    etype = clause.get("energy_type")
    if target == "any":
        # DEADNESS-ONLY (`FETCH_DEADNESS_ONLY_TARGETS`): every card in the zone is a legal find, so
        # the class can only ever be dead on an EMPTY zone — but it names no class, which is what
        # reach's endorsement set is made of. Gated here rather than left to the doctrine's target
        # filter, so the guarantee does not rest on one caller remembering to apply it.
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


#: What a card's revealing clauses mean TOGETHER — see :func:`reveal_legs`.
#:
#: ``relation`` is one of ``"single"`` / ``"union"`` / ``"conjunction"``; ``legs`` are the revealing
#: clauses in store order; ``cap`` is how many cards the whole play delivers (a union's shared
#: budget, or 1 per leg for a conjunction).
RevealLegs = NamedTuple("RevealLegs", [("relation", str), ("legs", tuple), ("cap", int)])


def reveal_legs(clauses) -> RevealLegs:
    """How a card's revealing clauses COMBINE — the ONE reader of the multi-leg relation.

    Both reveal nodes need this and neither may spell it twice: `board_expectation` owns the CHANCE
    node (a deck search, hidden zone, probabilities) and `board_choice` owns the CHOICE node (a
    visible zone, no probabilities). Before this, each refused a multi-leg card outright and each
    *guessed* the relation in its own refusal message.

    The relation is already in the data. ``CLAUSE_PARAMETERS["choice"]`` declares *"the clause is one
    alternative of a choose-one card"*, and the discriminator is that flag plus ``amount``::

        every leg `choice`  +  amounts EQUAL   -> UNION, shared cap = that amount (absent => 1)
        every leg `choice`  +  amounts DIFFER  -> EXCLUSIVE either-or  -> refuse
        no leg `choice`     +  >= 2 legs       -> CONJUNCTION, one card per leg
        some legs `choice`, some not           -> half-declared        -> refuse

    Cross-checked card-for-card against the engine, which draws the same three distinctions with
    three structurally different ops (`src/cgpy/defs/chain_overrides.json`): ONE op over a union
    filter (`anyOf`, `pokemonOrBasicEnergy`) for a union; `xDeckToHandBuckets` /
    `xDeckTakeSequenceAndShuffle` for a conjunction; `xDeckToHandEitherOr` for the exclusive shape.

    Raises ``ValueError`` — the caller owns the refusal sentence, because the two nodes format
    theirs differently (`board_expectation` prefixes the card id and name; `board_choice` prefixes
    the choice key) — in four cases:

    * **no revealing clause at all** — this option is a point transition, not a reveal node;
    * **an exclusive either-or** — the branches carry different budgets, so there is no single cap
      to enumerate over (1210 Brock's Scouting, *"up to 2 Basic Pokémon or 1 Evolution"*);
    * **a half-declared relation** — neither reading is available. No carrier ships;
      `snapshot_coverage.choice_relation_problems` is the tripwire that keeps it that way;
    * **a reach-gated leg of a MULTI-leg card** — a ``target`` in
      :data:`FETCH_DEADNESS_ONLY_TARGETS`. Those resolve for DEADNESS and never for REACH, so
      `fetch_target_matches` returns False for them at the default reading every pool walk uses: the
      leg matches nothing *structurally*, not merely on this board. Skipping it would enumerate
      three of Secret Box's four legs while reporting completeness — the three-quarters-of-a-card
      modelling `board_delta._play`'s clause-union gate exists to refuse. 1092 Secret Box and 1206
      Larry's Skill each carry one.

    **A SINGLE reach-gated leg is deliberately NOT refused here**, and the asymmetry is the whole
    point of the rule: with one leg there is no *other* leg to enumerate, so no partial answer can
    be manufactured. The card simply reaches nothing, which its caller already reports precisely and
    at the right altitude — `board_expectation`'s empty-pool refusal (*"no target it can reach is
    still unseen in my deck"*). Refusing here instead would move eight cards (Pokégear 3.0, Meowth
    ex, Roto-Stick, Miracle Headset, Larry's Skill's siblings…) off the refusal reasons that
    correctly describe them and onto one that does not.

    Note the further asymmetry with an EMPTY leg, which is not this function's business at all: a
    leg whose target class is fine but which finds nothing *on this board* is a pool fact the caller
    skips (the engine does the same — *"empty buckets skip with a tac bump"*). A reach-gated leg can
    never find anything on any board, which is a card fact."""
    from common.snapshot_coverage import REVEALING_CLAUSES
    legs = tuple(c for c in (clauses or ()) if c.get("kind") in REVEALING_CLAUSES)
    if not legs:
        raise ValueError("no `draw`/`fetch` clause, so this option is a point transition rather "
                         "than a reveal node")
    if len(legs) == 1:
        return RevealLegs("single", legs, _leg_cap(legs[0]))
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


def _leg_cap(clause: dict) -> int:
    """How many cards ONE leg delivers. Absent ``amount`` is 1 — the shape 1097/1142 print (*"a
    Pokémon or a Basic Energy card"*). ``"all"`` is not a number here and is left to the caller to
    resolve against a real pool, so it reads as 0 rather than being guessed at."""
    amount = clause.get("amount")
    if amount is None:
        return 1
    return amount if isinstance(amount, int) and not isinstance(amount, bool) else 0


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
