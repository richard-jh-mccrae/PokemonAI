"""The **reviewed-corrections ledger** — blunders already assessed in blunder-busting, excluded
from fresh work so each round only surfaces *new* patterns.

The Tuner's auto-reconciliation (ADR-0018) drops a blunder once a new Hypothesis *satisfies* it.
But a blunder that was assessed and **consciously set aside** — refuted (a bad correction, e.g. it
forgoes a Knock Out), deferred (valid but needs new infrastructure), or covered (already handled by
an existing rule) — keeps re-surfacing as a proposal / unsatisfied constraint every run. This ledger
records those dispositions so `tune.py` and `/blunder-buster` skip them.

The file is a single hand-editable JSON map at ``data/corrections/reviewed.json``, keyed by the
Correction's **Scope subject** (the same id the reports print, ``review_key``). One entry per
dispositioned subject::

    {
      "_note": "...",
      "81904451-37":     {"disposition": "refuted",  "reason": "forgoes a KO",   "round": "2026-06-27"},
      "81904451-t12s1":  {"disposition": "covered",  "reason": "plan_turn rung", "round": "2026-07-10"},
    }

Keys starting with ``_`` are comments. Append entries with ``tools/train/review_correction.py``.

**"the same id the reports print" was FALSE until Issue #250**, and load-bearingly so:
`tuner/report_md._at` printed the *Anchor* frame for every scope, so a record keyed
``86091435-t14s0`` was displayed as ``ep 86091435 f119``. An operator copied that string into the
writer — which took it as free text and checked it against nothing — and the resulting ruling
reached no record and voided nothing for twelve days. Two things now hold the claim up: `_at`
returns ``review_key``, and `resolve_locator` accepts the Anchor form regardless (ADR-0090).
`gates.orphan_rulings` asserts the ledger has no unreachable entry at all.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import DEFAULT_ROOT

DEFAULT_REVIEWED = DEFAULT_ROOT / "reviewed.json"

# The disposition vocabulary. `refuted` also drops from the weight fit (bad label must not
# pressure weights); `deferred` / `covered` just held off the fresh-work surfaces.
# `deferred` = evidenced CAPABILITY-GAP only (/blunder-buster mandate): fix is a designed-but-unbuilt
# roadmap layer, recorded w/ real-Pilot re-measure + fixture + docs/todo definition-of-done.
# A merely-missing signal/tag/enum is never deferred -> it is built (step 4b).
#
# `transposition` (ADR-0088 decision 6, Issue #239): the ruling STANDS but its `correct` names one
# of an INDISTINGUISHABLE set of options, so no agent can be scored on picking "the right one". Kept
# distinct from `refuted` because the ruling is not disowned — `81905522-75`'s pick is cited by
# ADR-0085 decision 4 to justify leg-scoped guards. Both VOID the label for the graders
# (`gates.VOIDING_DISPOSITIONS`), for opposite reasons.
#
# `fixed` / `deferred-multi-turn` were in the ledger for weeks while this tuple listed neither — the
# loader accepted them, `review_correction.py` would have rejected them. Adopted rather than migrated:
# both are plainly rulings that STAND, and the drift itself is what ADR-0088 decision 3's loud
# unrecognised-disposition path now guards against recurring.
#
# Kept in step with `gates.RECOGNISED_DISPOSITIONS` by a test — a word this writer accepts that the
# graders do not recognise is exactly the silence that made this list wrong in the first place.
DISPOSITIONS = ("refuted", "transposition", "deferred", "deferred-multi-turn", "covered", "fixed")


def anchor_form(correction) -> str:
    """``"<episode_id>-<frame>"`` — the **Anchor** frame spelling, for ANY scope.

    On a decision-scope record this IS the `review_key`, which is why that function ends by calling
    this one: the ``<ep>-<frame>`` shape is written down once. Off decision scope the two diverge,
    and the gap is the whole of Issue #250 — `tuner/report_md._at` printed *this* for every scope
    while the ledger was keyed by `review_key`, so `86091435-119` named a record keyed
    `86091435-t14s0`.
    """
    return f"{correction.episode_id}-{correction.decision.get('frame')}"


def review_key(correction) -> str:
    """The ledger key for a Correction — its Scope's subject, matching the report ids (ADR-0049):

    - ``decision`` → ``"<episode_id>-<frame>"``   (unchanged; the pre-Scope key)
    - ``turn``     → ``"<episode_id>-t<turn>s<seat>"``  (seat needed: turn 0 is the shared setup phase)
    So disposing of a Turn Correction never retires the Decision Corrections inside that Turn.
    """
    scope = getattr(correction, "scope", "decision")
    if scope == "turn":
        return f"{correction.episode_id}-t{correction.subject}s{correction.seat}"
    return anchor_form(correction)          # decision scope: the key IS the Anchor form


def _locator_maps(keyed) -> dict:
    """``{form: {locator string: canonical review_key}}`` over the corpus, in ONE pass.

    ``keyed`` is `gates.keyed_corrections()`'s ``[(Frame Key, Correction), ...]``. The Frame Key is
    READ from the pair, never re-derived here — re-deriving it would make this module a second
    place that knows how a frame is named, which is the exact defect ADR-0087 decision 2 forbids
    and the reason the corpus is injected rather than fetched.
    """
    maps = {"key": {}, "frame_key": {}, "id": {}, "anchor": {}}
    for frame_key, c in keyed:
        canonical = review_key(c)
        maps["key"][canonical] = canonical
        maps["frame_key"][frame_key] = canonical
        if getattr(c, "id", None):
            maps["id"][c.id] = canonical
        maps["anchor"].setdefault(anchor_form(c), canonical)
    return maps


#: Locator forms, MOST authoritative first. The ranking is load-bearing on exactly one case: a
#: string that is one record's `review_key` and a *different* record's anchor form. Resolving that
#: to the anchor would silently re-point a ruling at a record the operator never named, so the
#: canonical key wins and the ambiguity resolves the safe way.
_LOCATOR_FORMS = ("key", "frame_key", "id", "anchor")


def resolve_locator(locator: str, keyed) -> str | None:
    """The one canonical `review_key` a **Ruling Locator** names, or ``None`` (ADR-0090
    decision 2, Issue #250).

    Four accepted spellings, all of which the operator can legitimately be holding:

    * the canonical `review_key`      — ``86091435-t14s0``
    * the **Frame Key**               — ``86091435|0|turn|14`` (what a gate readout prints)
    * the ``Correction.id``           — ``948537a24fb2``
    * the **anchor form**             — ``86091435-119`` (what the *report* printed)

    **This is not a relaxation of ADR-0087 decision 2 — it is that rule applied to the writer.**
    The key is still DERIVED from the record; the operator merely supplies a way to find the
    record. Before this, `review_correction.py` took the key as free text and checked it against
    nothing, which is how two human rulings ended up ruling on nothing: one with the wrong episode
    (`85046350-10`; the record is ep 85045840 f10) and one with the wrong key shape
    (`86091435-119`; the record is turn-scoped, so its key is `86091435-t14s0`). Neither was stale.

    The corpus is INJECTED — `blunder/` must never import `gates`, and injection is also what lets
    the whole resolver be tested against stubs with no JSONL on disk.
    """
    if not locator:
        return None
    maps = _locator_maps(keyed)
    for form in _LOCATOR_FORMS:
        hit = maps[form].get(locator)
        if hit:
            return hit
    return None


def near_misses(locator: str, keyed) -> list[str]:
    """Canonical keys a REJECTED locator plausibly meant — sorted, possibly empty.

    Two deterministic rules, both read off the two real orphans, **UNIONED — never chained**:

    1. **Same frame number, different episode** — catches `85046350-10` → `85045840-10`, a digit
       slip between two episodes that live in the same store file.
    2. **Known episode, unknown subject** — the generalised anchor↔Scope-subject case. Orphan 2's
       literal spelling (`86091435-119`) now *resolves* via the anchor form rather than being
       suggested, which is rule 2 succeeding instead of guessing; what is left for it to catch is a
       locator naming a real episode and a subject nothing carries.

    Rule 2's block is listed **first**: getting the episode right is the stronger signal, because
    the operator was demonstrably looking at that episode's report.

    **The union is load-bearing, and was got wrong first.** Written as ``same_frame or
    same_episode``, rule 1 silently suppressed rule 2 whenever any other episode happened to carry
    the same frame number — on the real corpus `near_misses("86091435-120")` answered
    ``['82753102-120', '83667237-120']``, two unrelated episodes, while all eleven rulings in the
    operator's OWN episode were hidden. Confident, wrong, and concealing the right candidate.

    **No edit distance, no fuzzy matching, ever.** A confident wrong suggestion points at *someone
    else's human ruling*, and the entry it produces would be correctly-formed — therefore invisible
    to `gates.orphan_rulings`, which only sees keys that reach nothing. Silence is the safe failure;
    a plausible wrong answer is not. Note the shape that keeps this honest: several *candidates* are
    a prompt to look, whereas one confident answer invites a blind paste — so the rules widen the
    list rather than trying to pick.
    """
    if not locator or resolve_locator(locator, keyed):
        return []
    episode, _, subject = locator.partition("-")
    if not subject:
        return []

    same_frame, same_episode = set(), set()
    for _frame_key, c in keyed:
        if subject == str(c.decision.get("frame")) and str(c.episode_id) != episode:
            same_frame.add(review_key(c))                          # rule 1
        if str(c.episode_id) == episode:
            same_episode.add(review_key(c))                        # rule 2
    return sorted(same_episode) + sorted(same_frame - same_episode)


def load_reviewed(path: Path | str = DEFAULT_REVIEWED) -> dict:
    """Load the ledger as ``{key: entry}`` (comment keys starting with ``_`` dropped). Missing -> {}."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def partition_reviewed(corrections, reviewed: dict):
    """Split Corrections into ``(active, dispositioned)`` by the ledger. ``active`` are the ones to
    route this round; ``dispositioned`` is ``[(correction, entry)]`` already assessed (excluded)."""
    active, dispositioned = [], []
    for c in corrections:
        entry = reviewed.get(review_key(c))
        if entry:
            dispositioned.append((c, entry))
        else:
            active.append(c)
    return active, dispositioned
