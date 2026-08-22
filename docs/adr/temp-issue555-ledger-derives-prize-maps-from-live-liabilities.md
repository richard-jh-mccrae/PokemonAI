# ADR-TEMP-555 — Ledger derives Prize Maps from live liabilities

Decks declare sparse Prize Plan constraints for bodies they prefer to preserve or sacrifice; they
do not enumerate knockout routes. Ledger derives the live Prize Map from remaining prizes and
reachable prize liabilities, preserving forced-overrun strategy without combinatorial deck data.
Plans permit only ordered card-ID or Pokémon-Role `protect` and `offer` selectors, applied as soft
tie-breakers; conditional rules and a second numeric currency are excluded.

This narrows ADR-0172's neutral Indifference Set: a Prize Plan may order actions only when every
Ledger swing in that set is exactly equal. Near-equal swings still use its seeded neutral lottery.
The plan participates in effective behavior identity. As agreed for this cleanup, structural
overrun adds to the existing `prize.race` activation instead of creating a second coefficient.
This narrowly refines ADR-0157: raw prize differential and forced overrun are two provenances of
one prize-race fact and intentionally tune together.

The Damage Formula's Bellman-only context builder and its tests move into `deprecated/bellman`;
submission packages no longer carry that compatibility surface.
