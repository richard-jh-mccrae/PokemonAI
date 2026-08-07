"""Parametric Effect Clauses for Trainers — pure & lib-free (ADR-0032 item 6).

Where a Function Tag is the coarse boolean trigger (``heal``), an Effect Clause carries the
quantities the math reads: ``{kind, amount, restriction?, condition?, rider?}``, a card being a
LIST of clauses. Measured from the same engine probe records the tag classifier reads.

``amount`` is an int, ``all`` (override-authored), or None — semantically the LARGEST magnitude
the engine actually produced. A probe can under-measure, so merges keep the max observed and
hand-verified overrides replace their kind: read it as a measured upper bound, not a floor.

``restriction`` is a STATIC target-class gate (``active_only``, ``mega_only``, …), authored but
OBSERVED where the seeded board can discriminate — on conflict the OBSERVED value wins.
``condition`` is a DYNAMIC board-state gate: the clause whiffs unless the state holds when played."""
from __future__ import annotations

# Engine enum codes mirrored locally so this module stays lib-free (cg/api.py).
_LOG_DRAW = 4        # LogType.DRAW (one log per drawn card)
_LOG_MOVE_CARD = 6   # LogType.MOVE_CARD
_LOG_HP_CHANGE = 16  # LogType.HP_CHANGE (value = actual delta; >0 & not a counter = heal)
_AREA_HAND = 2       # AreaType.HAND
_AREA_DISCARD = 3    # AreaType.DISCARD
_AREA_ENERGY = 8     # AreaType.ENERGY (Energy attached to Pokémon in play)

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
    """Effect Clauses for one card from ONE probe record (+ overrides). Pure; no signal degrades to [].
    One record = one resolution: a concatenation of several games would fabricate riders."""
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
    """Merge clause lists by ``(kind, restriction, condition, rider)``; amounts combine by max. Distinct
    restriction/condition/rider variants stay separate clauses. Monotonic: merging never loses one."""
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
    """Map the classifier over the pool → ``{cardId: [clauses]}`` (clause-less omitted). ``records`` holds
    a LIST per card, each classified separately and merged by max; overrides then union in by kind."""
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
    """Stamp the kind-union onto a whole table — the post-ACCUMULATION step, so a stale pre-gate
    measurement cannot survive beside its gated override. Also ships override-only cards."""
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
    """True if the card is worth putting on the observation board: a heal clause whose restriction the
    board can discriminate. Out-of-vocabulary gates are skipped — the board must not guess."""
    return any(c.get("kind") == "heal" and c.get("restriction") in OBSERVABLE_RESTRICTIONS
               for c in clauses)


def derive_restriction(board: list[dict], offered) -> dict:
    """Turn an observed heal-target offer into a clause ``restriction``. Only a discriminating seeded
    board yields one; anything else is an explicit error record, never a guess."""
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
    """Stamp an OBSERVED restriction onto a card's heal clauses; returns ``(clauses, conflicts)``. On a
    conflict the engine wins. The result is max-merged, and non-heal clauses ride through."""
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
    """Stamp observed restrictions onto a whole table — runs AFTER ``apply_overrides``, so the
    engine-observed value outranks the hand-authored one. Returns ``(table, conflicts)``."""
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
    """Union this run's table into a prior run's — MONOTONIC: a clause once measured is never dropped
    and amounts only grow. Rebuild ``--fresh`` after a classify-rule or override change."""
    out: dict[int, list[dict]] = {}
    for cid in set(new) | set(prior):
        out[cid] = merge_clauses(new.get(cid, []), prior.get(cid, []))
    return {cid: cls for cid, cls in out.items() if cls}
