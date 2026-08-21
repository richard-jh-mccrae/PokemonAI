# ADR-TEMP-582 — Pokémon Roles are strategic jobs

Pokémon Roles remain authored deck or scouting doctrine because identical cards can serve different jobs in different
decks. The shared typed vocabulary admits precise jobs, rejects ambiguous umbrella aliases, and excludes opponent-target
directives; intrinsic mechanics remain Card Functions and target priority remains Opponent Strategy.

This replaces ADR-0148's decision to admit Brief target words directly into the Role vocabulary. The migration costs
changes to existing card, deck, and Brief declarations, but gives Ledger training and the #559 Opponent Snapshot one
unambiguous feature meaning per Role.
