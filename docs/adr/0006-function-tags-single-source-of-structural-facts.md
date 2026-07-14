# Function Tags are the single source of structural card facts; roles are tags-in-context

**Status.** Accepted, then **partially reversed 2026-06-24** (the revision note below): Depth 1 (the
`is_exclass`→tag reuse) was reverted and the shipped `card_functions.json` is **behavioral-only** — it
carries no `attacker`/`engine`/`prize_swing` tags, so Depths 2–3 never landed and `Scout._target_role`
still derives roles from `CardStat` (`is_ex_body` / `maxDamage`) rather than from tags. The
produce-once/consume-as-context principle stands for behavioral tags.

> **Revised 2026-06-24 — structural facts are NOT tagged; Function Tags are behavioral-only.**
> The six *structural* tags this ADR introduced — `prize_swing` (from `ex`/`megaEx`),
> `item`/`supporter`/`tool`/`stadium` (from `cardType`), and `ace_spec` (from `aceSpec`) — were
> removed from `classify_functions`. They merely restated `CardData` fields the **runtime already
> reads for free** from the engine, so tagging them only duplicated the source and bloated
> `card_functions.json`. The table now carries **only behavioral function** (draw / search / heal /
> poison / spread / …). The rest of this ADR still holds for *those* facts: `cards.py` predicates
> stay canonical for **offline** use, "produce once → consume as context" still governs tags→roles,
> and the runtime `prize_liability` role reads `CardData.ex`/`megaEx` **directly** rather than a
> `prize_swing` tag. **Depth 1** (the `is_exclass`→tag reuse) is reverted; Depth 2/3 apply to
> behavioral tags only. The original decision is kept below for the record.

**Context.** Card-intrinsic structural facts were derived independently in up to four
places, across two data shapes: `cards.py` predicates (`is_exclass`/`is_attacker`/
`is_engine`, over cards.json dicts), the offline dossier role-tagger
(`compile_scouting._dossier_intel`), the runtime `Scout._target_role` (over `CardStat`),
and the new `classify_functions` tags. "ex-class → extra prizes" was encoded **4×**,
"deals damage → attacker" **3×**. The incoming probe-derived behavioral tags would only
widen the divergence — the same fact spelled differently in each layer, drifting apart.

**Decision.** *Produce once, consume as context.*

- `cards.py` predicates (`is_pokemon`/`is_exclass`/`is_attacker`/`stage_rank`) plus
  `archetype.is_engine` are the **canonical definitions** of card-intrinsic facts — one
  source of truth. Nothing re-encodes "ex or megaEx" / "maxDamage > 0".
- `classify_functions` (`meta_tracker/card_functions.py`) **composes** those predicates
  (+ engine probe + curated override) into **Function Tags** — the canonical per-card
  structural vocabulary, compiled offline and shipped as `card_functions.json` for O(1)
  runtime lookup (the same offline-produce / runtime-consume split as ADR-0003).
- **Roles** (`attacker` / `prize_liability` / `engine`, in dossiers and the Read) are
  Function Tags surfaced in a threat/target slot — *derived from the tags*, never
  re-derived from raw fields or stats. `fragile_preevo` is the lone exception: it is
  evolution-line-*position*, not a card-intrinsic fact, so it stays bespoke.

Sequenced so the refactor lands with related work, not as a big-bang:
- **Depth 1 (done):** `classify_functions` reuses `is_exclass`.
- **Depth 2 (with the probe harness):** add `attacker`/`engine` tags (reusing
  `is_attacker`/`is_engine`); `_dossier_intel` maps tags → roles.
- **Depth 3 (after `card_functions.json` ships):** `Scout._target_role` consumes the
  shipped tags, retiring its `CardStat`-based re-derivation.

**Consequences.**
- One definition of each structural fact; adding one = a predicate + a tag rule,
  consumed everywhere. Tags bridge the offline-dict vs runtime-`CardStat` shape split
  that forced the duplication.
- `card_functions.json` becomes a **versioned data contract** (offline producer ↔ runtime
  consumer), like the scouting artifact — schema changes move both in lockstep.
- The runtime Scout gains a dependency on the shipped tag table (Depth 3); it must
  **degrade gracefully** if the table is absent (fail-safe, like `load_artifact`) so
  recognition still runs tag-less.
- `fragile_preevo` is the one deliberate, documented role computed from line context, not
  from tags.
- Rejected: per-layer independent derivation (simple/decoupled, but the drifting status
  quo); a shared runtime predicate layer over `CardStat` (blocked by the dict-vs-`CardStat`
  shape split — Function Tags bridge the two shapes instead).
