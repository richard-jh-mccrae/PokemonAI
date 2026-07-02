"""Parametric Effect Clauses for Trainers — pure & lib-free (ADR-0032 item 6).

Where a Function Tag is the coarse boolean routing trigger (``heal``), an **Effect
Clause** carries the quantities the math reads:
``{kind, amount, restriction?, condition?, rider?}``, a card being a *list* of clauses.
Measured from the same engine probe records the tag classifier reads — the
``HP_CHANGE.value`` / DRAW-count magnitudes ``classify_functions`` deliberately
discards are kept here. Tags stay boolean (ADR-0006 untouched).

v1 kinds (grown only from what probe records actually show):
  * ``heal``  — amount = per-target max of the actor's positive, non-counter
    ``HP_CHANGE`` values in one resolution (max, not sum: "heal 40 from each" logs one
    HP_CHANGE per target; the per-target magnitude is board-independent). A heal may
    carry a rider: ``bounce_energy_to_hand`` (own Energy ENERGY→HAND after the heal —
    Wally's Compassion) or ``discard_own_energy`` (ENERGY→DISCARD — Super Potion).
  * ``draw``  — amount = number of the actor's DRAW logs (one log per card).

``amount`` is an int, ``"all"`` (override-authored: heal-all), or None — semantically
the **largest magnitude the engine actually produced**. A probe can under-measure
(HP_CHANGE logs the *actual* delta, capped by the damage present), so merges keep the
max observed and hand-verified overrides replace their kind. Conditional counts
resolve to the best *observed* case (long combat games organically trigger
prize-count bonus modes — Lacey measured 8, not the base 4), so consumers read the
amount as a measured upper bound, not a guaranteed floor.

Two orthogonal gates, override-authored (text-verified against the engine's
``all_card_data`` texts — a probe log can't see *why* a select offered a target):
  * ``restriction`` — a STATIC target-class gate: which cards are eligible at all
    (``active_only``, ``mega_only``, ``arvens_pokemon``, ``psychic_only``,
    ``active_dragon_only``). The ``mega_only``/``active_only``/unrestricted subset is
    additionally **OBSERVED** from the engine (ADR-0032 item 6): a seeded board with a
    damaged bench Mega + a damaged non-Mega Active (probe_restrictions.py) shows which
    targets the heal select actually offers; :func:`derive_restriction` turns the offer
    into a restriction and :func:`upgrade_restriction` stamps it over the authored one
    (on conflict the OBSERVED value wins — the engine is the authority).
  * ``condition`` — a DYNAMIC board-state gate: the clause whiffs unless the state
    holds when played. Enum (grown only from actual card texts):
      - ``energy_3_plus`` — target has 3 or more Energy attached
        (Jumbo Ice Cream 1147).
      - ``remaining_hp_30_or_less`` — target has 30 HP or less remaining
        (Bianca's Devotion 1190).
      - ``played_supporter_this_turn`` — the player played a Supporter from hand
        this turn (Community Center 1242; symmetric — either player's turn).

Requirements (tests: tests/test_card_effects.py, tests/test_card_effects_engine.py):
  1. REQ-EFFECT-0001 heal amount measured from HP_CHANGE (actor-side, positive,
     non-counter; per-target max, not sum).
  2. REQ-EFFECT-0002 draw count measured (actor DRAW logs).
  3. REQ-EFFECT-0003 energy riders detected per-record: a heal *followed by* the
     actor's own ENERGY→HAND move = ``bounce_energy_to_hand``; ENERGY→DISCARD =
     ``discard_own_energy``. No heal (or move-before-heal) → no rider.
  4. REQ-EFFECT-0004 overrides union clause-level by kind: an override replaces ALL
     measured clauses of its kind (multi-clause overrides ship whole); other measured
     kinds survive.
  5. REQ-EFFECT-0005 sparse/absent probe degrades to [] — never raises.
  6. REQ-EFFECT-0006 table build: records classified per-record (no cross-record rider
     fabrication / draw summing), merged by max; clause-less cards omitted.
  7. REQ-EFFECT-0007 cross-run accumulation is monotonic max-merge ("all" tops ints;
     a once-measured clause is never dropped; ``--fresh`` resets).
  8. REQ-EFFECT-0008 runtime loader (``common/effects.py``): packaged-file lookup,
     O(1) ``clauses(card_id)``, fail-safe to empty when the file is absent.
  9. REQ-EFFECT-0009 engine smoke: a deterministic draw trainer measures its count.
 10. REQ-EFFECT-0010 engine smoke: unambiguous heal trainers measure their printed
     amounts (and Super Potion its discard rider).
 11. REQ-EFFECT-0011 ``condition`` gates pass through the override union verbatim;
     clauses differing only in condition are distinct (never max-collapsed).
 12. REQ-EFFECT-0012 ``apply_overrides``: the kind-union survives accumulation — the
     post-accumulate stamp replaces stale pre-gate clauses and ships
     probe-unreachable override-only cards.
 13. REQ-EFFECT-0013 ``derive_restriction``: an observed offer maps to
     mega_only / active_only / unrestricted only when the seeded board makes the
     exclusion informative; anything else is an explicit error, never a guess.
 14. REQ-EFFECT-0014 ``upgrade_restriction``: observed confirms or replaces the
     authored restriction (conflicts reported, engine wins); a sibling amount-mode
     clause survives when the observation matches another clause; upgraded twins
     max-merge.
 15. REQ-EFFECT-0015 ``apply_observed_restrictions``: table-level pass; only
     observed cards change; conflicts keyed by card.
 16. REQ-EFFECT-0016 probe board pure helpers (probe_restrictions.py): board
     snapshot / offered-target / healed-serial extraction, chip-attacker and
     sturdy-body picks, legal deck build.
 17. REQ-EFFECT-0017 engine smoke: Wally's Compassion observes mega_only live.
"""
from __future__ import annotations

# Engine enum codes mirrored locally so this module stays lib-free (cg/api.py).
_LOG_DRAW = 4        # LogType.DRAW (one log per drawn card)
_LOG_MOVE_CARD = 6   # LogType.MOVE_CARD
_LOG_HP_CHANGE = 16  # LogType.HP_CHANGE (value = actual delta; >0 & not a counter = heal)
_AREA_HAND = 2       # AreaType.HAND
_AREA_DISCARD = 3    # AreaType.DISCARD
_AREA_ENERGY = 8     # AreaType.ENERGY (Energy attached to a Pokémon in play)

_RIDER_DEST = {_AREA_HAND: "bounce_energy_to_hand", _AREA_DISCARD: "discard_own_energy"}


def _amount_rank(a) -> tuple:
    """Total order for amounts: None < any int < "all" (heal-all tops every number)."""
    if a == "all":
        return (2, 0)
    if isinstance(a, int):
        return (1, a)
    return (0, 0)


def _sorted_clauses(clauses: list[dict]) -> list[dict]:
    """Deterministic order so the shipped JSON is reproducible run-to-run."""
    return sorted(clauses, key=lambda c: str(c))


def _union_overrides(measured: list[dict], overrides: list[dict] | None) -> list[dict]:
    """Clause-level union by kind: overrides replace ALL measured clauses of their
    kind (multi-clause overrides ship whole); other measured kinds survive."""
    if not overrides:
        return _sorted_clauses(measured)
    kinds = {c.get("kind") for c in overrides}
    keep = [c for c in measured if c.get("kind") not in kinds]
    return _sorted_clauses(keep + [dict(c) for c in overrides])


def classify_effect_clauses(card: dict, *, probe: dict | None = None,
                            overrides: list[dict] | None = None) -> list[dict]:
    """Effect Clauses for one card from ONE probe record (+ overrides). Pure; never
    raises on sparse input — no signal degrades to ``[]``, like ``classify_functions``.

    One record = one resolution: riders pair a heal with a *later* energy move, so
    feeding a concatenation of several games would fabricate riders — the builder
    classifies per record and merges with :func:`merge_clauses` instead.

    Args:
        card: static card dict (unused in v1; kept for signature parity with
            ``classify_functions`` and future kinds).
        probe: ``{actor, logs, contexts}`` record from one probe pass, or None.
        overrides: hand-authored clause list; replaces measured clauses of the same
            ``kind`` wholesale (the override is engine-text-verified truth — a probe
            may under-measure a capped heal). ``restriction``/``condition`` gates
            ride through verbatim.

    Returns:
        Sorted list of clause dicts ``{kind, amount, restriction?, condition?, rider?}``.
    """
    del card  # v1 reads nothing static; parity with classify_functions
    clauses: list[dict] = []
    if probe:
        actor = probe.get("actor")
        heal_amount = 0
        heal_seen_at: int | None = None
        rider: str | None = None
        draws = 0
        for i, lg in enumerate(probe.get("logs") or []):
            if lg.get("playerIndex") != actor:
                continue                       # opponent-side events aren't my clause
            t = lg.get("type")
            if t == _LOG_DRAW:
                draws += 1
            elif t == _LOG_HP_CHANGE and (lg.get("value") or 0) > 0 \
                    and not lg.get("putDamageCounter"):
                heal_amount = max(heal_amount, lg.get("value"))
                if heal_seen_at is None:
                    heal_seen_at = i
            elif (t == _LOG_MOVE_CARD and heal_seen_at is not None and i > heal_seen_at
                    and lg.get("fromArea") == _AREA_ENERGY):
                rider = _RIDER_DEST.get(lg.get("toArea"), rider)  # heal → own Energy off
        if heal_amount > 0:
            cl: dict = {"kind": "heal", "amount": heal_amount}
            if rider:
                cl["rider"] = rider
            clauses.append(cl)
        if draws > 0:
            clauses.append({"kind": "draw", "amount": draws})

    # Curated overrides: clause-level union by kind — the hand-verified clause(s)
    # replace every measured clause of that kind (Arven's two heal modes ship whole).
    return _union_overrides(clauses, overrides)


def merge_clauses(*lists: list[dict]) -> list[dict]:
    """Merge clause lists by ``(kind, restriction, condition, rider)`` — amounts
    combine by max.

    Distinct restriction/condition/rider variants stay separate clauses (Arven's two
    heal modes; a gated heal never collapses into an ungated one); same-key clauses
    keep the largest amount observed (a capped-heal pass never shadows a
    fully-damaged one). Monotonic: merging never loses a clause.
    """
    merged: dict[tuple, dict] = {}
    for clauses in lists:
        for c in clauses or []:
            key = (c.get("kind"), c.get("restriction"), c.get("condition"), c.get("rider"))
            prev = merged.get(key)
            if prev is None or _amount_rank(c.get("amount")) > _amount_rank(prev.get("amount")):
                merged[key] = dict(c)
    return _sorted_clauses(list(merged.values()))


def build_effect_table(cards: dict[int, dict], records: dict[int, list[dict]] | None = None,
                       overrides: dict[int, list[dict]] | None = None) -> dict[int, list[dict]]:
    """Map the classifier over the pool → ``{cardId: [clauses]}`` (clause-less omitted).

    ``records`` holds a LIST of probe records per card (one per pass) — each is
    classified separately (riders and counts are per-resolution facts) and the clause
    lists merged by max. Overrides then union in by kind.
    """
    records = records or {}
    overrides = overrides or {}
    table: dict[int, list[dict]] = {}
    for cid, card in cards.items():
        per_rec = [classify_effect_clauses(card, probe=r) for r in records.get(cid, [])]
        measured = merge_clauses(*per_rec) if per_rec else []
        clauses = _union_overrides(measured, overrides.get(cid))
        if clauses:
            table[cid] = clauses
    return table


def apply_overrides(table: dict[int, list[dict]],
                    overrides: dict[int, list[dict]] | None) -> dict[int, list[dict]]:
    """Stamp the kind-union onto a whole table — the post-**accumulation** step.

    Accumulation is monotonic, so a stale pre-gate measurement in the prior table
    (Bianca's capped ungated 250) would survive beside its gated override (distinct
    merge key). Applying the union *after* accumulating replaces every clause of an
    overridden kind with the hand-verified truth, and ships override-only cards the
    probe can't reach (Dragon Elixir, Community Center)."""
    if not overrides:
        return table
    out = dict(table)
    for cid, ovr in overrides.items():
        merged = _union_overrides(out.get(cid, []), ovr)
        if merged:
            out[cid] = merged
    return out


# Restrictions the observation board can discriminate (see derive_restriction).
# Type gates (psychic_only, active_dragon_only) need typed boards — not observable here.
OBSERVABLE_RESTRICTIONS = frozenset({None, "active_only", "mega_only"})


def restriction_observable(clauses: list[dict]) -> bool:
    """True if the card is worth putting on the observation board: it has a heal
    clause whose restriction the board can discriminate. Cards gated ONLY by
    out-of-vocabulary restrictions (Jacinthe's psychic_only) are skipped — the board
    can't separate a type gate from an active gate and must not guess."""
    return any(c.get("kind") == "heal" and c.get("restriction") in OBSERVABLE_RESTRICTIONS
               for c in clauses)


def derive_restriction(board: list[dict], offered) -> dict:
    """Turn an observed heal-target offer into a clause ``restriction`` (REQ-EFFECT-0013).

    ``board`` is my in-play snapshot at play time (``{serial, mega, active, damaged}``
    per body — probe_restrictions.snapshot_board); ``offered`` the serials the engine's
    select actually offered (or auto-healed). The seeded board — damaged Mega on the
    Bench, damaged non-Mega Active — makes one offer discriminating:

      * only Megas offered while a damaged non-Mega was excluded  -> ``mega_only``
      * only the Active offered while a damaged benched body was excluded -> ``active_only``
      * both classes offered                                       -> ``None`` (unrestricted)

    Anything else — nothing offered, an uninformative board (no damaged body was
    *excluded*), an offer no vocabulary value explains — is ``{"error": reason}``,
    never a guess.
    """
    by_serial = {b.get("serial"): b for b in board}
    off = [by_serial[s] for s in dict.fromkeys(offered or []) if s in by_serial]
    if not off:
        return {"error": "nothing_offered"}
    excluded = [b for b in board if b not in off]
    megas = [b for b in off if b.get("mega")]
    non_megas = [b for b in off if not b.get("mega")]
    if megas and non_megas:
        return {"restriction": None}
    if megas:
        if any(b.get("damaged") and not b.get("mega") for b in excluded):
            return {"restriction": "mega_only"}
        return {"error": "no_damaged_non_mega_excluded"}
    if all(b.get("active") for b in off):
        if any(b.get("damaged") and not b.get("active") for b in excluded):
            return {"restriction": "active_only"}
        return {"error": "no_damaged_benched_excluded"}
    return {"error": "ambiguous_offer"}


def upgrade_restriction(clauses: list[dict], observed) -> tuple[list[dict], list[tuple]]:
    """Stamp an OBSERVED restriction onto a card's heal clauses (REQ-EFFECT-0014).

    * observed matches a clause -> confirmed; differing siblings are amount-modes
      (Arven's ``arvens_pokemon``) and survive untouched.
    * unrestricted measured clause -> takes the observed restriction (the probe never
      measures restrictions; this is the normal upgrade, not a conflict).
    * authored restriction differs and nothing matched -> CONFLICT: observed wins
      (engine is authority), the ``(authored, observed)`` pair is reported.

    Returns ``(clauses, conflicts)``; the result is max-merged so an upgraded twin
    collapses into an equal-key authored clause. Non-heal clauses ride through.
    """
    heals = [c for c in clauses if c.get("kind") == "heal"]
    if not heals:
        return list(clauses), []
    matched = any(c.get("restriction") == observed for c in heals)
    out: list[dict] = []
    conflicts: list[tuple] = []
    for c in clauses:
        if c.get("kind") != "heal" or c.get("restriction") == observed:
            out.append(dict(c))
        elif c.get("restriction") is None:                    # measured, ungated
            out.append({**c, "restriction": observed})
        elif matched:                                         # sibling amount-mode
            out.append(dict(c))
        else:                                                 # authored gate vs engine
            conflicts.append((c.get("restriction"), observed))
            nc = dict(c)
            if observed is None:
                nc.pop("restriction", None)
            else:
                nc["restriction"] = observed
            out.append(nc)
    return merge_clauses(out), conflicts


def apply_observed_restrictions(table: dict[int, list[dict]],
                                observed: dict[int, dict] | None
                                ) -> tuple[dict[int, list[dict]], dict[int, list[tuple]]]:
    """Stamp observed restrictions onto a whole table (REQ-EFFECT-0015) — runs AFTER
    ``apply_overrides`` so the engine-observed value outranks the hand-authored one.
    ``observed`` maps ``cardId -> {"restriction": ...}`` (extra provenance keys
    ignored); cards absent from the table are ignored. Returns ``(table, conflicts)``.
    """
    if not observed:
        return table, {}
    out = dict(table)
    conflicts: dict[int, list[tuple]] = {}
    for cid, entry in observed.items():
        if cid not in out:
            continue
        upgraded, conf = upgrade_restriction(out[cid], entry.get("restriction"))
        out[cid] = upgraded
        if conf:
            conflicts[cid] = conf
    return out, conflicts


def accumulate_effects(new: dict[int, list[dict]],
                       prior: dict[int, list[dict]]) -> dict[int, list[dict]]:
    """Union this run's table into a prior run's — **monotonic**, like
    ``accumulate_tables``: a clause once measured is never dropped, and amounts only
    grow (max-merge), so successive stochastic combat passes converge on the printed
    heal value. Rebuild ``--fresh`` after a classify-rule or override change."""
    out: dict[int, list[dict]] = {}
    for cid in set(new) | set(prior):
        out[cid] = merge_clauses(new.get(cid, []), prior.get(cid, []))
    return {cid: cls for cid, cls in out.items() if cls}
