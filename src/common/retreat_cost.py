"""**The Retreat Cost a body actually pays** — the grant-aware read, in one place (ADR-0100 §8).

*"To retreat, you must discard 1 Energy from your Active Pokémon for each [C] listed in its Retreat
Cost. If no [C] are listed, it retreats for free"* (`docs/rulebook.txt` L142). The printed number is
`CardStat.retreatCost`, and three shipped card shapes move it, so the printed number is not the
answer:

1. a flat attached-Tool reduction — Air Balloon (1174) *"is {C}{C} less"*, `retreatReduction` **+2**;
   Gravity Gemstone *"is {C} more"*, **−1**, which is why the delta is SIGNED and a retreat can cost
   MORE than printed (Issue #306);
2. a CONDITIONAL attached Tool — Rescue Board (1157) *"If that Pokémon's remaining HP is 30 or less,
   it has no Retreat Cost"*, `retreatFreeAtHp`;
3. a BOARD-LEVEL Ability on ANOTHER of my bodies — Latias ex (184) Skyliner, *"Your Basic Pokémon in
   play have no Retreat Cost"*, `retreatFreeGrant`. The granting body is not the body retreating, so
   no per-card read could ever see it, and the engine cannot supply it either: `retreatCost` exists
   only on `CardData` as the static printed value.

Every read fails **CLOSED** — an unreadable or unmodelled grant charges the PRINTED cost, erring
toward not retreating and never toward the retreat-happy pathology the ADR-0100 grill opened on.

## A FOURTH grant shape exists, is unmodelled, and was measured rather than reasoned about

**Ethan's Magcargo (356)**, Ability *Melt Away*: *"If this Pokémon has no Energy attached, it has no
Retreat Cost"* (`data/EN_Card_Data.csv`, printed text). That is a SELF Ability conditional on the
body's own attachment count — none of the three shapes above — and nothing parses it, so
`CardStat.retreatFreeGrant` is `None` for 356 and this module charges its printed **3**.

Found by `tools/train/choice_parity.py`, not by inspection: 2 corpus steps
(`cnt_lavaburst_9980` f32 and its `micro_` twin) where the engine offered and resolved a retreat that
cost **0** Energy from a body carrying none, while this read said 3. The choice node REFUSES those
steps, which is the correct fail-closed answer for a synthesis, and the lane counts them in its
backlog rather than hiding them.

⚠️ **The Pilot has the same gap, and it is not new here.** `Pilot._effective_retreat_cost` has always
charged the printed cost for this card, so ADR-0100's `retreat_cost(A)` over-states a Magcargo pivot
by the full convex build delta. Closing it needs a `scouting/card_text.py` parse and a new `CardStat`
field, which changes what the affordability gate believes on any board holding a bare Magcargo — a
decision-moving change, so it is RECORDED here rather than smuggled into Issue #392's build.

## Why this is a module and not a Pilot method (Issue #392)

It was a Pilot method (`Pilot._effective_retreat_cost`) until `common.board_choice` needed the same
fact: the size of a retreat's Energy-discard target space **is** this number, so a choice node that
computed it for itself would be a second reader of a fact ADR-0070 already drew the lesson for —
*"one function owns the fact, so the readings cannot disagree"* (`_build_standing`). The Pilot's
three methods are now one-line delegations to this module; nothing about the arithmetic changed, and
`tests/scouting/test_retreat_cost_grants.py` grades it through the Pilot exactly as before.

⚠️ **This does NOT discharge the divergence that file names.** `Pilot._can_retreat`,
`planner._promotion_ease` and `planner._retreat_shortfall` read the printed cost minus the SIGNED
Tool delta and consult **no board-level grant**, so on a board with Latias ex benched they still
answer differently from this module. That reconciliation is owed to Issue #149 and is deliberately
untouched here: changing what the affordability gate believes would move corpus decisions, which is
a ruling this issue does not hold.
"""
from __future__ import annotations

from common.strategy.context import _METAL


def attached_tool_stats(body: dict | None, stat_of):
    """The ``CardStat`` of every Tool attached to ``body``.

    The ONE place the engine's ``tools`` list is resolved — it appears as bare ids AND as id-carrying
    dicts, both shapes in the committed corpus. Unknown ids are skipped, so a caller only ever sees
    Tools it can actually read."""
    if not body or stat_of is None:
        return
    for tool in (body.get("tools") or []):
        tid = tool.get("id") if isinstance(tool, dict) else tool
        tstat = stat_of(tid) if tid is not None else None
        if tstat is not None:
            yield tstat


def attached_retreat_delta(body: dict | None, stat_of) -> int:
    """Σ ``retreatReduction`` over the Tools attached to ``body`` — the amount to SUBTRACT from a
    printed Retreat Cost.

    SIGNED, and that is the point (Issue #306): Gravity Gemstone parses to −1, so the sum can be
    negative and the arithmetic stopped being a subtraction of non-negatives. Four call sites had
    each open-coded the loop, which is how one of them (``_retreat_shortfall``) came to omit it
    entirely — survivable while every Tool was a discount, unsound the moment one is a surcharge,
    because that site sizes a `KO_SCORE`-class claim."""
    return sum(getattr(t, "retreatReduction", 0) for t in attached_tool_stats(body, stat_of))


def retreat_free_granted(active: dict | None, stat, *, my_bodies=(), stat_of, combat) -> bool:
    """Does a BOARD-LEVEL Ability of mine give ``active`` no Retreat Cost (ADR-0100 §8)?

    The predicate travels WITH the grant (`CardStat.retreatFreeGrant`), so adding a card adds a parse
    and a predicate rather than a call-site special case. An unknown predicate → False, which is the
    fail-closed direction: we charge the printed cost.

    ``my_bodies`` is every in-play body on MY side (Active and Bench), because the granting body is
    by construction not the one retreating.

    ⚠️ **This could not fire at all until Issue #408**, and the note is carried here from
    `Pilot._retreat_free_granted` — the method this module replaced — rather than lost with it.
    `CardStat.stage` was declared and never written, so the ``"basic"`` predicate below compared
    against `None` for every card in the pool. It was dead for TWO independent reasons: that, and the
    fact that the only deck carrying the grantor (`slowking`, 2x Latias ex) has no `strategy.py` and
    so is never built as a Pilot. Issue #408 removed the first; the second is Issue #149's to close,
    and until it does this stays latent rather than live. Worth stating plainly because the grant was
    modelled, covered by tests, and reachable by neither route — the tests declared `stage` themselves.

    Verified through THIS module after the extraction and after Issue #408: a Basic at printed
    Retreat Cost 2 reads **0** with Latias ex in play and **2** without, so the woken predicate
    survives the move intact.

    The ``.lower()`` is redundant against a real provider — `stage` is the canonical
    ``"basic"``/``"stage1"``/``"stage2"`` from `provider.stage_from_card` — and is kept because the
    field crosses a provider boundary and a cheap coercion beats a silent miss on an injected row."""
    if not active or stat is None or stat_of is None:
        return False
    for body in my_bodies or ():
        cid = (body or {}).get("id")
        gstat = stat_of(cid) if cid is not None else None
        grant = getattr(gstat, "retreatFreeGrant", None) if gstat is not None else None
        if grant == "basic" and (getattr(stat, "stage", None) or "").lower() == "basic":
            return True
        if grant == "metal_attached" and combat is not None \
                and combat.attached_type_counts(active).get(_METAL):
            return True
    return False


def effective_retreat_cost(active: dict | None, *, stat_of, my_bodies=(), combat=None) -> int:
    """The Active's Retreat Cost in Energy — the count of Energy a retreat actually discards, and so
    (ADR-0100 §8) both the size of the build a retreat destroys and the size of the Energy-discard
    dimension `common.board_choice` enumerates.

    READ-ONLY: this mirrors the cost arithmetic of the affordability gate without its verdict, and
    returns 0 on an unknown stat rather than guessing.

    The three grant shapes resolve in the order the rules make them bite — a conditional Tool zeroes
    the cost outright before any arithmetic, then the signed flat delta, then the board-level grant
    (which only ever *removes* a cost that survived the delta). Under the old flat `x ENERGY_TIER`
    pricing a missed reduction cost 8 points; under the convex build delta, over-charging one Energy
    on a 3-slot attacker is `(3/3)^2 - (2/3)^2 = 5/9 x maxDamage` ~ **117 damage of phantom cost**,
    and it would be systematic on an archetype built around free-retreat pivoting."""
    if not active or stat_of is None:
        return 0
    stat = stat_of(active.get("id"))
    if stat is None:
        return 0
    hp = active.get("hp") or 0
    for tstat in attached_tool_stats(active, stat_of):
        free_at = getattr(tstat, "retreatFreeAtHp", 0)
        if free_at and hp and hp <= free_at:
            return 0                                  # Rescue Board on a damaged holder
    cost = getattr(stat, "retreatCost", 0) - attached_retreat_delta(active, stat_of)
    if cost > 0 and retreat_free_granted(active, stat, my_bodies=my_bodies, stat_of=stat_of,
                                         combat=combat):
        return 0
    return max(0, cost)


__all__ = ("attached_tool_stats", "attached_retreat_delta", "retreat_free_granted",
           "effective_retreat_cost")
