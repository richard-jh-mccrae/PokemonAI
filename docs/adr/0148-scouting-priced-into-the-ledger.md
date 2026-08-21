# ADR-0148 — Scouting priced into the Ledger: opponent roles, Brief overrides, turn ordering

Status: Superseded by Issue #582. Follows ADR-0145/0146/0147.

## Context

The Ledger valued the opponent's board at almost nothing: the unified store (ADR-0143) covers
only our three decks' 50 printings, so nearly every opponent card fell to
`unknown_card_worth = 0.05`, non-lethal damage was near-worthless, and 18 of 19 snipe/gust
target menus priced every option exactly 0.0 (the decider also constructed its providers bare
— no `registry`/`effects`/`stats` — so fact-needing transitions like bench damage failed and
scored zero). Meanwhile the scouting machinery already knows opponents: the Read recognizes
archetypes with a confidence ramp (`posture_gamma`), Briefs declare each archetype's Pokémon
WITH roles, and `general_pokemon_roles` mints deck-agnostic roles from function tags — none of
it reached the Ledger. Owner directive 2026-08-20: wire scouting in, aligned with our own role
definitions — opponent roles get a general weighting, each Brief can override.

Hand-authoring store records for the 122 unknown ids was rejected: the store's discipline
(fail loud on unencoded effects) would force full effect encoding per card, and the Ledger
needs opponent WORTH, not opponent transitions. Scouting legitimately owns the whole-pool
legacy tables, so opponent knowledge enters through that sanctioned seam and the store stays
the fact base for our own cards.

## Decision

- **`OpponentLayer`** (`ledger/worth.py`): per-decision scouting for THEIR side's worth reads.
  `roles` = card-generic claims for bodies/discards the opponent has shown (full strength —
  card knowledge needs no recognition). `brief_roles` = recognition claims (matched Brief's
  declarations via `resolve_brief_cards`, plus Read intel) and `weights` = the general vector
  bent by the Brief's new `ledger_overrides` block — both blended by the Read's gamma:
  `worth = general + gamma x (scouted - general)`, so gamma 0 is exactly the general read
  (fail-open). One `base_worth`, one new `own=` switch; our side never reads the layer.
- **One role table, both sides**: the Brief target vocabulary (`disruption_target`,
  `support_pokemon`, `engine`) joins `ROLE_WORTH`; only scouted opponent bodies carry those
  roles. Briefs override in the same dotted-key format decks use; a typo raises at layer
  build, loud.
- **Provider fidelity**: `LedgerDecider` passes the runtime's `registry`/`effects`/`stats`
  into provider construction; Damage-context transitions now resolve and a KO snipe prices
  its prize (pinned on frame 82749168-50).
- **Turn ordering, two refinements to spend-then-end**: a root `Refresh` is a hand-ender —
  plays whose value survives the shuffle go first, the shuffle next, and discard-recycling
  plays (`_RESTOCK_TAGS = {recycle, recycle_line}`, read off the played card in the identity
  parts) queue behind it — their whole yield is hand cards the shuffle would throw away. The
  tag set is deliberately narrow: rulings want bench-fillers, info items and tutors FIRST
  (yield benched, read, or played before the shuffle); a broad fetch/draw set was measured
  and LOST frames (179 vs 185 agrees). `act_threshold` becomes a weight (default 0.0 = the
  historical any-positive bar), separated from the float-noise tie-break.
- **Lever hygiene**: every live store tag is a priced lever (new ones at 0.0 = kind-fallback
  behavior until a round raises them; dead `recovery` deleted); special energy prices through
  its own `kind.special_energy`.

## Consequences

- Corpus (after ADR-0147's baseline): floor 32.6% → 34.8%, lucario 33.9% → 39.3%, starmie
  39.1% → 42.6% (agrees 169 → 185 of 447); 5 target-choice frames now price targets but
  chase the free KO over the ruled threat, and a handful of supporter-substitution frames
  (Mega Signal / Hilda vs Lillie's) still mis-rank — tuning targets, no longer coverage
  holes.
- Store expansion for opponents is explicitly NOT the path; a future record still wins over
  the unknown floor whenever one is authored.
