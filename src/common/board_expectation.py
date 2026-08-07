"""**The expectation node** — a reveal's outcome classes, closed-form (POC-T4/2, Issue #383), under the
seam contract ADR-0098 froze at POC-T0.

`board_delta` answers *"what board would this produce?"* for a DETERMINISTIC option: one option, one
board. A draw or a search has no *a* result, it has a DISTRIBUTION, and the honest seam returns the
distribution rather than a sampled representative. This builds it: the outcome classes, their
probabilities from `deck_odds`' shipped closed forms, and a fresh `StateModel` per class.
`apply_option` owns the frozen `OutcomeClass` / `Expectation` shapes; this only fills them.

**Still INERT at runtime** — nothing imports this module. Verified, not assumed.

Never a sampled engine shuffle (Issue #178). The class identity is taken AFTER the reveal, never on
the deck reference. The zone split, the gate order, `BRANCH_CAP` and the measured apply-seam coverage
are ADR-0130; the equivalence collapse is ADR-0091; one store per ADR-0087. Card facts and rules are
read at source per CLAUDE.md, never recalled."""
from __future__ import annotations

from typing import NoReturn

from collections import Counter
from itertools import product

from common import board_delta, deck_odds, snapshot_coverage
from common.board_delta import Unmodellable
from common.fetch_closure import (fetch_is_unconditional, fetch_target_matches,
                                  multiset_classes, reveal_legs)
from common.option_equivalence import AREA_HAND, option_fingerprint
from common.strategy.context import _PLAY

#: **The branching cap** — the maximum outcome classes one Expectation enumerates. The measured
#: post-Option-Equivalence menu-width P95; see this module's header for the derivation and for the
#: cross-check against the grader's own per-decision floor. A structural constant chosen from a
#: measurement, never a tuned strategy weight, and truncation past it is ALWAYS reported
#: (`Expectation.truncated` and the `total_probability` gap).
BRANCH_CAP = 12

#: Clause keys this module knows how to honour. Anything else refuses, fail-closed against vocabulary
#: drift — the same rule `board_delta._clause_writes` keeps for clause VALUES. Every member is also a
#: `snapshot_coverage.CLAUSE_PARAMETERS` key, so this set can only ever narrow that registry.
#:
#: `cost` / `cost_required` are deliberately ABSENT rather than listed-and-ignored: a costed search
#: refuses, and listing the key would make that refusal look like an oversight.
_HANDLED_FETCH_KEYS = frozenset({
    "kind", "target", "zone", "amount", "dest",
    # target predicates, every one of them resolved by the shipped `fetch_target_matches`
    "energy_type", "hp_max", "no_rule_box", "no_ability",
    # the RELATION between several revealing legs — a union's shared cap versus a conjunction's one
    # card per leg. Read by `fetch_closure.reveal_legs`, which both reveal nodes share, since Issue
    # #394; before that it was inert and this comment called it "a flag that only says the player
    # picks", which is not what `CLAUSE_PARAMETERS` declares it to mean.
    "choice",
    # the play's price, applied BEFORE the search from a caller-supplied `shed` oracle. `cost` names
    # the count via `snapshot_coverage.COST_CARDS`; `cost_required` is the playability half of the
    # same fact and needs no separate handling here, because an unpayable cost already refuses as an
    # illegal play rather than a free one.
    "cost", "cost_required",
})


def revealing_clauses(combat, card_id) -> tuple:
    """This card's `draw` / `fetch` clauses — the ones `snapshot_coverage.REVEALING_CLAUSES` names.

    Read off the compendium through the combat oracle's own `CardEffects`, so a card the compendium
    has never heard of yields `()` and the caller refuses. **An empty tuple is never evidence that a
    card reveals nothing** — it is evidence that nothing is DECLARED, which is the clause-less blind
    spot `apply_option.footprints_writing_unhomed` names by card (Premium Power Pro 1141, Black
    Belt's Training 1211, Brave Bangle 1175)."""
    return tuple(c for c in board_delta.card_clauses(combat, card_id)
                 if c.get("kind") in snapshot_coverage.REVEALING_CLAUSES)


def _legs_of(combat, card_id, stat):
    """This card's revealing legs and how they COMBINE, or :class:`Unmodellable`.

    The relation itself is `fetch_closure.reveal_legs` — ONE reader, shared with `board_choice`'s
    CHOICE node, because both nodes face the same question and a second spelling is how the two
    would come to disagree about the same card. It raises `ValueError` with the reason; this wraps it
    in the seam's own ``"<id> <name>: …"`` convention.

    Before Issue #394 this function refused every multi-leg card and *guessed* the relation in the
    refusal — *"printed as a CONJUNCTION … nothing in the clause vocabulary distinguishes AND from
    OR"*. Both halves were wrong: `choice` distinguishes them, and 69 of the 98 refused corpus steps
    were unions rather than conjunctions.

    The companion-clause refusal stays HERE rather than moving into the shared reader: it is a fact
    about what this node can price (a non-revealing leg would difference to exactly 0 in every class
    it enumerates), not about what the card's reveal legs mean, and `board_choice` answers it
    differently for its own node."""
    every = board_delta.card_clauses(combat, card_id)
    name = getattr(stat, "name", "?")
    try:
        legs = reveal_legs(every)
    except ValueError as gap:
        _no(card_id, name, str(gap))
    if len(every) > len(legs.legs):
        _no(card_id, name, "it carries a non-revealing clause as well, whose leg would "
                                  "difference to exactly 0 in every enumerated class")
    return legs


def _no(card_id, name, why) -> NoReturn:
    """Raise the seam's one refusal, in the seam's one convention: ``"<id> <name>: <what is
    missing>"`` (`apply_option.EngineResolved.clause_gap`). The message is destined for the telemetry
    line and the modelling backlog, which is grouped by exactly this string."""
    raise Unmodellable(f"{card_id} {name}: {why}")


def _check_clause(clause: dict, card_id, name) -> None:
    """Every fail-closed gate on the clause itself, in one place so a caller cannot forget one.

    **Ordered most-specific-first, and the order is load-bearing.** The unknown-KEY gate is the
    catch-all and it runs LAST, because every gate above it names a key that IS legitimate clause
    vocabulary and answers with the actionable reason: a `dig` should refuse as *"not the
    unconditional whole-deck search"* rather than as *"unrecognised key `dig`"*, and a shuffling
    `rider` should refuse as *"consults RNG"* rather than as *"unrecognised key `rider`"*. A backlog
    grouped by the catch-all's message is a backlog nobody can act on."""
    for value in snapshot_coverage.clause_values(clause):
        if value in snapshot_coverage.NONDETERMINISTIC_CLAUSES:
            _no(card_id, name, f"clause {value!r} consults RNG — a simulated shuffle is one sample, "
                               f"not a distribution (the engine has no deal-seed)")
    if clause.get("kind") == "draw":
        _no(card_id, name,
            "a `draw` is an n-card window and `deck_odds` answers *P(>=1 target in the window)*, "
            "never the JOINT distribution over which n cards arrived; single-card classes would be a "
            "conditional biased toward the highest-count cards, which is worse than the search "
            "case's honest lower bound")
    if not fetch_is_unconditional(clause):
        _no(card_id, name, "not the unconditional, decidable whole-deck search "
                           "`fetch_closure.fetch_is_unconditional` defines — it carries a `trigger`, "
                           "a `dig`, a `condition` or a `name_family`, none of which this seam can "
                           "decide")
    if clause.get("zone") != "deck":
        _no(card_id, name, f"a {clause.get('zone')!r}-zone search carries NO chance — that zone is "
                           f"visible — so it is a pure CHOICE node, not an expectation")
    cost = clause.get("cost")
    if cost is not None:
        if cost not in snapshot_coverage.COST_CARDS:
            _no(card_id, name, f"cost {cost!r} is not in `snapshot_coverage.COST_CARDS` — fail "
                               f"closed against vocabulary drift, exactly as this module's "
                               f"unknown-key gate does")
        if snapshot_coverage.COST_CARDS[cost] is None:
            _no(card_id, name, f"cost {cost!r} names no fixed card count. `discard_hand` pays the "
                               f"whole hand, whose size is not a constant; `bottom_2` returns cards "
                               f"to the DECK, which moves `unseen_counts` and would invalidate the "
                               f"pool this node enumerates over")
    amount = clause.get("amount")
    if amount is not None and not (isinstance(amount, int) and not isinstance(amount, bool)
                                   and amount >= 1):
        _no(card_id, name, f"`amount` {amount!r} names no number the enumerator can range over — "
                           f"only `\"all\"` reaches here, and resolving it needs a pool to count "
                           f"against plus the Bench cap its carriers deliver into (Issue #410)")
    if clause.get("dest") is not None:
        _no(card_id, name, f"`dest` {clause.get('dest')!r}: the found body arrives IN PLAY, which is "
                           f"the deploy transition with its Bench cap and Stadium-trigger gate, not "
                           f"a hand write")
    unknown = sorted(set(clause) - _HANDLED_FETCH_KEYS)
    if unknown:
        _no(card_id, name, f"clause key(s) {unknown} are not in this module's handled set — fail "
                           f"closed against vocabulary drift, exactly as `board_delta._clause_writes` "
                           f"refuses an undeclared clause VALUE")


def outcome_pool(model, clause: dict) -> dict:
    """``{card id: unseen copies}`` — the deck cards this search can deliver.

    The candidate set is `MySide.unseen_counts` (my decklist minus everything provably outside the
    deck) and the filter is the SHIPPED `fetch_closure.fetch_target_matches`, never a second matcher:
    that predicate is the one place the target vocabulary is resolved, and ADR-0087 charges for a
    hand-built second key exactly here. Its default REACH reading is the one taken, so a class it
    gates (`supporter`, `any`) yields nothing and the caller refuses rather than over-claiming."""
    return {cid: n for cid, n in (model.mine.unseen_counts or {}).items()
            if n > 0 and fetch_target_matches(clause, model.card_stat(cid))}


def _class_weight(model, delivered: tuple) -> float:
    """The availability weight of ONE outcome class — ADR-0029's hypergeometric prize split, asked
    per distinct card at the MULTIPLICITY that class needs.

    A class is a tuple of delivered card ids, so a conjunction whose legs both reach the same card,
    or a multi-card delivery that takes two copies of one, needs *two copies still in the deck* —
    which is `deck_odds.p_contains_at_least(..., k)`, not `p_contains`. For a single-card class this
    is exactly the old `p_contains` call, bit for bit, which is why the shipped classes do not move.

    The per-card factors are MULTIPLIED, and that is an availability weight rather than a joint draw
    probability — the epistemics this module's header already states (*"a class's probability is an
    availability weight, normalised over the enumerated set"*). Not normalised here: the caller
    normalises over the FULL class set before capping, so truncated mass shows up as a
    `total_probability` below 1.0 instead of vanishing."""
    hidden, left = model.mine.prizes_hidden, model.mine.deck_count
    unseen = model.mine.unseen_counts or {}
    weight = 1.0
    for cid, need in Counter(delivered).items():
        weight *= deck_odds.p_contains_at_least(unseen.get(cid, 0), hidden, left, need)
    return weight


def _cost_indices(model, option, legs, *, seat_index, card_id, name, shed) -> tuple:
    """The HAND INDICES this play's cost takes, ``()`` when it is free, or a refusal.

    **The seam, not a second formula.** WHICH cards a cost discards is a live decision the Pilot's
    `needs.cheapest_removal` already makes at the real select; this node must assume the set that
    decider would pick, so the answer is passed IN by whoever holds a Pilot. With no oracle supplied
    it REFUSES and names the missing seam — it never prices the cost unpaid, which would over-value
    every Ultra Ball by the two cards it does not charge for.

    Indices are validated against the hand and de-duplicated, and the played card is excluded: the
    engine's own gate is `handOthers`, *"discard 2 OTHER cards"*."""
    costs = {leg.get("cost") for leg in legs.legs if leg.get("cost") is not None}
    if not costs:
        return ()
    if len(costs) > 1:
        _no(card_id, name, f"its legs declare DIFFERENT costs {sorted(costs)} — a play has one "
                           f"price, so this is either a compendium defect or a shape with no single "
                           f"payment to charge; refusing rather than picking one")
    cost = costs.pop()
    picks = snapshot_coverage.COST_CARDS[cost]          # `_check_clause` proved it is a real count
    if shed is None:
        _no(card_id, name, f"its cost {cost!r} takes {picks} card(s) from my hand and no `shed` "
                           f"oracle was supplied — WHICH cards is the live decider's answer "
                           f"(`needs.cheapest_removal`), so the caller must pass it in rather than "
                           f"have this node invent a second one")
    hand = ((model.source_obs.get("current") or {}).get("players") or [{}])[seat_index].get("hand")
    played = option.get("index")
    taken = tuple(dict.fromkeys(int(i) for i in (shed(model, option, picks) or ())))
    legal = tuple(i for i in taken if 0 <= i < len(hand or ()) and i != played)
    if len(legal) != picks:
        _no(card_id, name, f"its cost takes {picks} card(s) and the `shed` oracle named {len(legal)} "
                           f"usable hand index(es) — the play is not legal on this board (the "
                           f"engine's own `handOthers` gate), so there is nothing to enumerate")
    return legal


def _revealed(model, option, delivered: tuple, *, seat_index, stat, paid: tuple = ()):
    """The observation after the search RESOLVES: the source card in my discard, the found card(s) in
    my hand, and the Supporter allowance spent if one was.

    Copy-on-write throughout — `board_delta`'s own scaffolding, reused rather than re-spelled, so a
    hypothetical board and its pre-state share every zone the reveal did not touch. Those three
    helpers were PROMOTED to public names for this consumer (Issue #383); reaching for the underscore
    versions would be the cross-module private reach `state_model.py` documents as *"how a refactor
    inside `MySide` breaks a caller nothing warned about"*. Their `PlayerState` is never reached
    across, which is what lets the caller rebuild with ``reuse_their_side=True``.

    The source card is spent ONCE per play, never once per delivered card — a conjunction is one
    Supporter resolving into several picks, not several plays.

    ``paid`` are the hand indices this play's cost takes, applied BEFORE the search — the engine's
    own order (`chain_overrides.json` 1121: ``play: [costHandTrash, effectDeckToHandAndShuffle]``).
    The order is observable rather than cosmetic: charging after would let a delivered card be
    discarded to pay for its own search. Removed highest-index-first so the earlier indices stay
    valid, and the played card's index is re-resolved afterwards for the same reason."""
    new_obs, current, players = board_delta.fork(model.source_obs)
    me = board_delta.fork_player(players, seat_index)
    index = option.get("index")
    if paid:
        hand = list(me.get("hand") or ())
        spent = [hand[i] for i in sorted(paid, reverse=True)]
        for i in sorted(paid, reverse=True):
            hand.pop(i)
        me["hand"] = hand
        if me.get("handCount") is not None:
            me["handCount"] = len(hand)
        me["discard"] = list(me.get("discard") or ()) + list(reversed(spent))
        index = index - sum(1 for i in paid if i < index)      # the play's own index shifts down
    played = board_delta.take_from_hand(me, index, "reveal")
    # `docs/rulebook.txt` L78 — the card that performed the search is out of play once it resolves.
    me["discard"] = list(me.get("discard") or ()) + [played]
    # The found cards, synthesized: the deck is face-down, so they have no observed `serial`. That is
    # the ONE field ADR-0091's fingerprint ignores, which is precisely why a synthesized instance is
    # sound to fingerprint — and it is negative so an eye on a dump can tell it from an engine one.
    # The ORDINAL is what keeps it unique: `-card_id` alone collides the moment one class delivers
    # two copies of the same card, which a conjunction over overlapping legs and every multi-card
    # delivery can both do.
    hand = list(me.get("hand") or ())
    at = []
    for ordinal, card_id in enumerate(delivered):
        hand.append({"id": card_id, "serial": -(card_id * 100 + ordinal),
                     "playerIndex": seat_index})
        at.append(len(hand) - 1)
    me["hand"] = hand
    if me.get("handCount") is not None:
        me["handCount"] = len(hand)
    if me.get("deckCount") is not None:
        me["deckCount"] = max(0, int(me["deckCount"]) - len(delivered))
    if getattr(stat, "is_supporter", False):
        current["supporterPlayed"] = True          # `docs/rules.md` §3 — one Supporter per turn
    return new_obs, tuple(at)


def _fingerprint(obs, indices: tuple, seat_index) -> tuple:
    """The outcome class's identity — `option_equivalence.option_fingerprint` over the card(s) this
    class put in my HAND, on the POST-reveal board.

    A tuple of per-card fingerprints, which is why `OutcomeClass.fingerprint` was declared a tuple:
    a multi-card delivery is several cards arriving from one play, and its identity is all of them.
    Never taken on the pre-reveal deck reference: that option is unfingerprintable by design (Issue
    #263 § *duplicate-cards*), and giving it a partial identity is what that section forbids."""
    return tuple(option_fingerprint({"type": _PLAY, "area": AREA_HAND, "index": index,
                                     "playerIndex": seat_index}, obs)
                 for index in indices)


def _classes_for(legs, pools: tuple) -> list:
    """The outcome classes a card's legs deliver, as sorted tuples of card ids. ``[]`` when the legs
    can deliver nothing at all, which the caller turns into the empty-pool refusal.

    * **single / union** — one pool. A union's is the UNION of its legs' pools, built with the same
      walk `fetch_closure.class_reaccess_outs` already performs for a needs slot's re-supply: a card
      reached by either leg is reachable once, not twice.
    * **conjunction** — the cross product, one card per leg, and **an empty leg SKIPS**. That is the
      engine's own behaviour, not a convenience: `chain_overrides.json`'s provenance for 1231 Dawn
      records *"empty buckets skip with a tac bump"*. Measured, Dawn's product is 0 on all 8 of its
      corpus steps precisely because two of its three legs are empty — enumerating nothing there
      would refuse a card the engine resolves happily. Refuse only when EVERY leg is empty."""
    if legs.relation == "conjunction":
        live = [sorted(p) for p in pools if p]
        if not live:
            return []
        return sorted({tuple(sorted(combo)) for combo in product(*live)})
    union: dict = {}
    for pool in pools:
        union.update(pool)
    return multiset_classes(union, legs.cap)


def expectation(model, option, *, seat_index=None, context=None, cap: int = BRANCH_CAP,
                shed=None):
    """The :class:`~common.apply_option.Expectation` over ``option``'s reveal, or
    :class:`~common.board_delta.Unmodellable`.

    ``context`` defaults to the live select context on the model's own observation, so a caller
    holding a real board does not have to dig it out; ``seat_index`` defaults to the model's seat.
    ``cap`` defaults to :data:`BRANCH_CAP` and is a parameter because the composer's budget is
    per-decision rather than global — a wide menu may want a tighter cap than a two-option one — and
    because truncation is otherwise untestable without a 30-card fixture. It must be **>= 1**: a cap
    of 0 would return a zero-class Expectation, which is precisely the shape the empty-pool refusal
    exists to prevent, so it raises rather than manufacturing one.

    The header carries the epistemics: a class's ``probability`` is an availability weight, so
    ``expected()`` is a LOWER bound on the choice node's true max and the composer is where the max
    is taken."""
    from common.apply_option import Expectation, OutcomeClass          # contract, imported lazily

    if int(cap) < 1:
        raise ValueError(
            f"cap={cap!r}: an Expectation must enumerate at least one class — a zero-class one is an "
            f"un-enumerated effect whose `expected()` raises, which is the shape the empty-pool "
            f"refusal exists to prevent. Caller error, so it raises where a modelling gap refuses.")
    obs = getattr(model, "source_obs", None)
    if not obs:
        raise Unmodellable("the model carries no source observation to reveal from — it was "
                           "constructed directly rather than through `StateModel.build`")
    seat_index = int(getattr(model, "my_index", 0) if seat_index is None else seat_index)
    if context is None:
        context = (obs.get("select") or {}).get("context")
    if context != board_delta.CONTEXT_MAIN:
        raise Unmodellable(
            f"select context {context!r} is not the MAIN menu — this option is one leg of a card's "
            f"effect resolving, and that card's other writes ride the same engine step")
    kind = int((option or {}).get("type", -1))
    if kind != _PLAY:
        raise Unmodellable(
            f"option kind {kind} is not a `_PLAY` — a reveal riding another kind does not put its "
            f"source card in my discard, so this module's structural floor does not hold for it")

    hand = ((obs.get("current") or {}).get("players") or [{}])[seat_index].get("hand") or ()
    index = option.get("index")
    if not isinstance(index, int) or not 0 <= index < len(hand):
        raise Unmodellable(f"reveal names hand index {index!r}, which this snapshot cannot resolve "
                           f"(hand of {len(hand)})")
    card_id = (hand[index] or {}).get("id")
    stat = model.card_stat(card_id)
    if stat is None:
        raise Unmodellable(f"{card_id}: no `CardStat` for the played card")
    name = getattr(stat, "name", "?")
    # *"Does this option reveal at all?"* is asked FIRST, ahead of every other gate, so the backlog
    # groups by the actionable answer: a Basic deploy is not an under-scoped expectation node, it is
    # not an expectation node. Measured — the order moved 79 corpus steps out of the card-type
    # bucket and into "no `draw`/`fetch` clause", where they belong.
    legs = _legs_of(model.combat, card_id, stat)
    # Then the ABILITY gate, and it runs ahead of the card-type floor because it answers a different
    # question and a sharper one. A reveal declared on a body is usually an ABILITY — Lunatone's
    # `{"kind": "draw", "condition": "solrock_in_play"}`, Fezandipiti ex's `pokemon_ko_last_turn` —
    # and an Ability does not fire because the body was PLAYED; it is a separate `_ABILITY` option.
    # So deploying the body reveals NOTHING, and modelling it would be flatly wrong rather than
    # under-scoped. The one shape that does ride the `_PLAY` is an on-bench-play trigger.
    #
    # Behind it, the clause gates run BEFORE the card-type floor, so a card with a real defect in
    # its clause (a `trigger`, a `dig`) refuses on THAT rather than on being a Pokemon. Measured:
    # 11 steps land on the ability gate (Lunatone 7, Fezandipiti ex 4) and 12 on the reach predicate
    # (Meowth ex, whose `supporter` target and `on_bench_play` trigger are both real), leaving 0 at
    # the floor — which is the point. A backlog row nobody can act on is a row that lies.
    if not (getattr(stat, "is_item", False) or getattr(stat, "is_supporter", False)):
        triggers = {leg.get("trigger") for leg in legs.legs}
        if triggers != {"on_bench_play"}:
            named = sorted(t for t in triggers if t)
            carried = f"trigger(s) {named}" if named else "no `trigger` at all"
            _no(card_id, name, f"its revealing clause is an ABILITY, not this play — it carries "
                               f"{carried}, and only `on_bench_play` fires because the body was "
                               f"PLAYED (an Ability is a separate `_ABILITY` option). So deploying "
                               f"it reveals nothing, and modelling a reveal here would be WRONG "
                               f"rather than under-scoped")
    for leg in legs.legs:
        _check_clause(leg, card_id, name)
    if not (getattr(stat, "is_item", False) or getattr(stat, "is_supporter", False)):
        _no(card_id, name, "only an Item or a Supporter resolves to my discard on a search; this "
                           "card's structural floor is a different one")

    paid = _cost_indices(model, option, legs, seat_index=seat_index, card_id=card_id, name=name, shed=shed)
    pools = tuple(outcome_pool(model, leg) for leg in legs.legs)
    candidates = _classes_for(legs, pools)
    if not candidates:
        _no(card_id, name, "no target it can reach is still unseen in my deck — a provably-whiffing "
                           "search is a fact to refuse on, not a zero-class Expectation")
    weights = {klass: _class_weight(model, klass) for klass in candidates}
    mass = sum(weights.values())
    if mass <= 0.0:
        _no(card_id, name, "no target it can reach has any availability left (`deck_odds` puts every "
                           "matching copy outside the deck), so there is nothing to enumerate")

    # Descending weight, then ascending class: the ordering must be a pure function of the board or
    # two processes enumerate different sets, which is the reproducibility guarantee
    # `option_equivalence.class_representatives` keeps for exactly the same reason.
    ranked = sorted(candidates, key=lambda klass: (-weights[klass], klass))
    kept, dropped = ranked[:int(cap)], ranked[int(cap):]
    classes = []
    for klass in kept:
        after_obs, at = _revealed(model, option, klass, seat_index=seat_index, stat=stat,
                                  paid=paid)
        classes.append(OutcomeClass(
            probability=weights[klass] / mass,
            # The reveal never reaches across the table, so their already-built side is reusable —
            # `board_delta.Delta.shares_opponent`'s guarantee, held here by construction.
            model=model.rebuilt(after_obs, reuse_their_side=True),
            fingerprint=_fingerprint(after_obs, at, seat_index)))
    return Expectation(classes=tuple(classes), truncated=len(dropped))


__all__ = ("BRANCH_CAP", "revealing_clauses", "outcome_pool", "expectation")
